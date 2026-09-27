"""The settle call (spec section 5): while any candidate is live, each
utterance also gets one small typed call, alongside the decision call,
asking whether it settles one of them at the table.

- It runs only while at least one candidate is live: being checked, waiting
  for the screen, or on screen. It first waits until the decision on every
  earlier utterance is known, so a candidate flagged two seconds earlier
  isn't missed. Backchannel utterances are skipped, as for the decision call.
- It uses the decision model and the decision call's context window, but only
  the date and time, with no place. It lists only the live candidates flagged
  before the utterance, each by its standalone restatement (the raw utterance
  until one arrives); a candidate on screen also shows its card's fact.
- Its choices are `none`, `settles Cn` for each live candidate not yet on
  screen, and `agrees with Cn` and `disputes Cn` for the one on screen (as
  the page last reported). A choice counts from `decision.settle_threshold`
  (`settle_outcome`).
- `settles Cn` drops Cn if its card still isn't on screen
  (`Checker.drop`): its check's results are thrown away, a card already sent
  is withdrawn, and the recording keeps `silent:settled` with the settling
  utterance's id. The settling utterance goes through the decision call like
  any other, so a false correction gets its own check.
- `agrees with Cn` is recorded and shows nothing yet; the "Settled at the
  table" mark comes in the next version. `disputes Cn` adds nothing to the
  card, and the disputing utterance isn't checked separately, since the card
  on screen already answers it: a candidate flagged in it is dropped
  (`silent:disputing`). A card in the card history never changes.
- A failed call is never retried, and its failure is recorded
  (`Session.failure`). It counts toward the decision model's "Can't check"
  with the decision calls (`carl.outages`). Each call is recorded and charged like a decision
  call, as the `settle` stage.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Collection, Mapping, Sequence
from typing import Any

from .decision import Candidate, account, context, is_backchannel, line, position
from .location import date_time
from .models import ModelError, TypedModel
from .models.questions import TypedPrompt
from .session import Heard, Session, Sessions

log = logging.getLogger(__name__)

STAGE = "settle"
NONE = "none"
SETTLES, AGREES, DISPUTES = "settles Cn", "agrees with Cn", "disputes Cn"
NOTHING_BEFORE = "(nothing said before)"


def settle_outcome(answer: str, probs: Mapping[str, float] | None, choices: Collection[str],
                   threshold: float) -> tuple[str, float | None]:
    """The settle call's outcome and its probability: the most likely choice
    other than `none` that names a candidate, if its own probability reaches
    `threshold`; otherwise `none`. Mass pooled over several candidates
    (`settles *`) names none, so it settles nothing. With no probabilities,
    the chosen answer is taken as it is."""
    if probs is None:
        return answer, None
    named = {c: p for c, p in probs.items() if c in choices and c != NONE}
    best = max(named, key=named.__getitem__, default=None)
    if best is not None and named[best] >= threshold:
        return best, named[best]
    return NONE, probs.get(NONE)


def live_line(candidate: Candidate, fact: str | None = None) -> str:
    """`C3: restatement`, with the card's fact for a candidate on screen."""
    text = f"{candidate.id}: {candidate.shown_as}"
    return f"{text} [on screen: {fact}]" if fact else text


def fields(utterance: str, conversation: Sequence[str], when: str, live: Sequence[str]) -> dict[str, str]:
    """The settle call's named text fields, from their lines."""
    return {
        "date_time": when,
        "live_candidates": "\n".join(live),
        "conversation": "\n".join(conversation) or NOTHING_BEFORE,
        "utterance": utterance,
    }


class Settler:
    """The settle call for every session's utterances: `sessions.settler`."""

    def __init__(self, sessions: Sessions, model: TypedModel) -> None:
        self.sessions, self.model = sessions, model
        self.prompt = TypedPrompt.load(sessions.prompts["settle"])
        self.backchannel = frozenset(w.lower() for w in sessions.config.decision.backchannel)

    async def on_utterance(self, session: Session, heard: Heard, earlier: Collection[asyncio.Task] = ()) -> None:
        """The settle call on one utterance, once the decisions still running
        on earlier utterances (`earlier`) are known. Runs as its own task."""
        try:
            if earlier:
                await asyncio.wait(earlier)
            await self.settle(session, heard)
        except Exception:
            log.exception("session %s: the settle call on %s went wrong", session.id, heard.id)

    def live(self, session: Session, heard: Heard) -> list[Candidate]:
        """The live candidates flagged in utterances before `heard`."""
        before = {id(item) for item in session.heard[:position(session.heard, heard)]}
        return [c for c in session.candidates if c.live and id(c.heard) in before]

    async def settle(self, session: Session, heard: Heard) -> None:
        if is_backchannel([w.text for w in heard.utterance.words], self.backchannel):
            return
        live = self.live(session, heard)
        if not live:
            return
        on_screen = [c for c in live if c.state == "on screen"]
        waiting = [c for c in live if c.state != "on screen"]
        s = self.sessions.config.decision
        before = session.heard[:position(session.heard, heard)]
        conversation = [line(item) for item in context(before, heard, s.context_utterances, s.context_window_s)]
        lines = [live_line(c, self.fact(session, c) if c in on_screen else None) for c in live]
        ids = {SETTLES: [c.id for c in waiting], AGREES: [c.id for c in on_screen],
               DISPUTES: [c.id for c in on_screen]}
        question = self.prompt.fill(fields(line(heard), conversation, date_time(session.timezone), lines), ids)
        try:
            answer = await self.model.ask(question, stage=STAGE)
        except ModelError as e:
            await account(self.sessions, session, heard, question, e.record)
            session.failure(STAGE, e.kind, record=e.record)
            session.health.call(ok=False)
            session.log("settle", utterance=heard.id, outcome="failed", error=e.kind)
            log.warning("session %s: %s; no settle call on %s", session.id, e, heard.id)
            return
        await account(self.sessions, session, heard, question, answer.record)
        session.health.call(ok=True)
        chosen, probability = settle_outcome(answer.answer, answer.probs, question.choices, s.settle_threshold)
        event: dict[str, Any] = {"utterance": heard.id, "answer": answer.answer, "probs": answer.probs,
                                 "outcome": chosen, "probability": probability}
        if chosen == NONE:
            session.log("settle", **event)
            return
        cid = chosen.rsplit(" ", 1)[1]
        candidate = next(c for c in session.candidates if c.id == cid)
        checker = self.sessions.checker
        if chosen.startswith("settles "):
            applied = checker is not None and await checker.drop(session, candidate, "silent:settled",
                                                                 settled_by=heard.id)
            session.log("settle", **event, candidate=cid, applied=applied)
        elif chosen.startswith("disputes "):
            session.disputing[heard.id] = cid
            session.log("settle", **event, candidate=cid, applied=True)
            for flagged in [c for c in session.candidates if c.heard is heard and c.live]:
                if checker is not None:
                    await checker.drop(session, flagged, "silent:disputing", disputes=cid)
        else:  # agrees: recorded only, until the next version's mark
            session.log("settle", **event, candidate=cid, applied=False)

    @staticmethod
    def fact(session: Session, candidate: Candidate) -> str | None:
        card = session.cards.get(candidate.id)
        return None if card is None else card.content.get("fact")


def install(sessions: Sessions) -> None:
    """Plug the settle call into the sessions (`sessions.settler`), with the
    decision call's own model. Without the decision call, there is none."""
    if sessions.decider is not None:
        sessions.settler = Settler(sessions, sessions.decider.model)
