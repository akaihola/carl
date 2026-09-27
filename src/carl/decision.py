"""The decision call (spec section 5): one typed call per utterance, deciding
whether it holds a claim or an open question worth checking, or repeats an
earlier candidate. Candidates are recorded, not shown, until step 4.

- Every utterance gets its own call, running to the end as its own task, so
  a newer utterance never cancels one. Only an utterance made up entirely of
  backchannel words (the config's `decision.backchannel`) is skipped; it
  still appears in later calls' context.
- The call is given the utterance, as the one judged; up to
  `context_utterances` earlier ones from no more than `context_window_s`
  before it, with the "(paused)" and "(gap)" markers between them; the
  place and local time; and the session's earlier candidates by Carl's ids,
  C1, C2…
- A speaker label is only valid within its own speech-to-text stream, so
  each stream gets its own letter: stream 1's speaker 1 is A1, stream 2's
  is B1.
- A failed call drops its utterance and is never retried, since a card
  minutes late is worthless. Its cost, an estimate if need be, is charged
  like any other.
"""

from __future__ import annotations

import inspect
import logging
import string
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from .language import CardLanguage, card_language
from .location import date_time
from .models import CallRecord, ModelError, Question, TypedAnswer, TypedModel, http_session, make_typed_model
from .models.questions import TypedPrompt
from .session import Heard, Marker, Session, Sessions

log = logging.getLogger(__name__)

STAGE = "decision"
SAME_AS = "same as "
KINDS = ("claim", "open question")
NOTHING_BEFORE = "(nothing said before)"
NO_CANDIDATES = "(none yet)"
# Stripped from each end of a word before it is looked up in the backchannel list.
PUNCTUATION = string.punctuation + "…“”‘’«»–—"


@dataclass
class Candidate:
    """An utterance the decision call flagged as a claim or an open question."""

    id: str  # C1, C2…
    kind: Literal["claim", "open question"]
    heard: Heard
    probability: float | None  # of its kind; None when the vendor gave no probabilities
    card_language: CardLanguage
    restatement: str | None = None  # the first fact-finder's standalone restatement (step 4)
    state: str = "recorded"

    @property
    def shown_as(self) -> str:
        """How later decision calls list it: its restatement, or its raw utterance until one arrives."""
        return self.restatement or self.heard.utterance.text

    def event(self) -> dict[str, Any]:
        return {"id": self.id, "kind": self.kind, "utterance": self.heard.id, "probability": self.probability,
                "card_language": self.card_language.event()}


def is_backchannel(words: Sequence[str], backchannel: Collection[str]) -> bool:
    """True if every word, lower-cased and without punctuation, is on the (lower-case) list."""
    return all(bare in backchannel for w in words if (bare := w.strip(PUNCTUATION).lower()))


def stream_letters(stream: int) -> str:
    """A for stream 1, B for stream 2… Z, then AA, AB…"""
    letters = ""
    while stream > 0:
        stream, rest = divmod(stream - 1, 26)
        letters = chr(ord("A") + rest) + letters
    return letters


def line(item: Heard | Marker) -> str:
    """An utterance as `A1: text`, with its speaker label unique across streams, or a marker."""
    if isinstance(item, Marker):
        return f"({item.kind})"
    return f"{stream_letters(item.stream)}{item.utterance.speaker}: {item.utterance.text}"


def position(heard: Sequence[Heard | Marker], item: Heard) -> int:
    """Where `item` is in the session's list. Anything heard after it comes later."""
    for i in range(len(heard) - 1, -1, -1):
        if heard[i] is item:
            return i
    raise ValueError(f"{item.id} is not among the session's utterances")


def context(before: Sequence[Heard | Marker], heard: Heard, most: int, window_s: float) -> list[Heard | Marker]:
    """What the call is shown of `before` (everything said before `heard`):
    up to `most` utterances, none more than `window_s` before it, with the
    markers between them. A marker with nothing before it in the window is
    left out, since there is no break to show."""
    picked: list[Heard | Marker] = []
    count = 0
    for item in reversed(before):
        if isinstance(item, Heard):
            if count == most or heard.time - item.time > window_s:
                break
            count += 1
        picked.append(item)
    while picked and isinstance(picked[-1], Marker):
        picked.pop()
    return picked[::-1]


def fields(utterance: str, conversation: Sequence[str], place_and_time: str, earlier: Sequence[str]) -> dict[str, str]:
    """The decision call's named text fields, from their lines."""
    return {
        "place_and_time": place_and_time,
        "earlier_candidates": "\n".join(earlier) or NO_CANDIDATES,
        "conversation": "\n".join(conversation) or NOTHING_BEFORE,
        "utterance": utterance,
    }


def outcome(answer: str, probs: Mapping[str, float] | None, repeat_threshold: float,
            candidate_threshold: float) -> tuple[str, float | None]:
    """From probabilities to an outcome (spec section 5): `same as Cn`,
    `claim`, `open question` or `none`, with its probability.

    1. The `same as` choices together at `repeat_threshold` or more make a
       repeat of the most likely one. When their mass is pooled as `same as
       *`, so that no candidate can be named, it is a repeat of an unknown
       candidate (`same as *`), which gets nothing: precision over recall.
    2. Otherwise `claim` and `open question` together at
       `candidate_threshold` or more make a candidate of the more likely
       kind.
    3. Otherwise `none`.

    With no probabilities, the chosen answer is taken as it is.
    """
    if probs is None:
        return answer, None
    same = {choice: p for choice, p in probs.items() if choice.startswith(SAME_AS)}
    if sum(same.values()) >= repeat_threshold:
        named = {choice: p for choice, p in same.items() if choice != SAME_AS + "*"}
        if not named:
            return SAME_AS + "*", sum(same.values())
        best = max(named, key=named.__getitem__)
        return best, named[best]
    claim, question = probs.get("claim", 0.0), probs.get("open question", 0.0)
    if claim + question >= candidate_threshold:
        return ("claim", claim) if claim >= question else ("open question", question)
    return "none", probs.get("none")


class LazyModel:
    """A typed model made on its first call: its HTTP session needs the running event loop."""

    def __init__(self, make: Callable[[], TypedModel]) -> None:
        self.make = make
        self.model: TypedModel | None = None

    async def ask(self, question: Question, *, stage: str) -> TypedAnswer:
        if self.model is None:
            self.model = self.make()
        return await self.model.ask(question, stage=stage)


class Decider:
    """The decision call for every session's utterances."""

    def __init__(self, sessions: Sessions, model: TypedModel) -> None:
        self.sessions, self.model = sessions, model
        self.prompt = TypedPrompt.load(sessions.prompts["decision"])
        self.settings = sessions.config.decision
        self.backchannel = frozenset(w.lower() for w in self.settings.backchannel)

    async def on_utterance(self, session: Session, heard: Heard) -> None:
        """Decide on one utterance. Runs as its own task, to the end."""
        try:
            await self.decide(session, heard)
        except Exception:
            log.exception("session %s: the decision on %s went wrong", session.id, heard.id)

    async def decide(self, session: Session, heard: Heard) -> None:
        if is_backchannel([w.text for w in heard.utterance.words], self.backchannel):
            session.log("decision skipped", utterance=heard.id)
            return
        s = self.settings
        before = session.heard[:position(session.heard, heard)]
        conversation = [line(item) for item in context(before, heard, s.context_utterances, s.context_window_s)]
        earlier = list(session.candidates)
        question = self.prompt.fill(
            fields(line(heard), conversation, await self.place_and_time(session),
                   [f"{c.id}: {c.shown_as}" for c in earlier]),
            [c.id for c in earlier],
        )
        try:
            answer = await self.model.ask(question, stage=STAGE)
        except ModelError as e:
            await self.account(session, heard, question, e.record)
            session.log("decision", utterance=heard.id, outcome="dropped", error=e.kind)
            log.warning("session %s: %s; %s is dropped", session.id, e, heard.id)
            return
        await self.account(session, heard, question, answer.record)
        chosen, probability = outcome(answer.answer, answer.probs, s.repeat_threshold, s.candidate_threshold)
        decided = {"utterance": heard.id, "answer": answer.answer, "probs": answer.probs}
        if chosen.startswith(SAME_AS):
            matched = chosen.removeprefix(SAME_AS)
            matched = None if matched == "*" else matched  # a repeat, but of which candidate is unknown
            session.log("repeat", utterance=heard.id, candidate=matched, probability=probability)
            session.log("decision", outcome="repeat", candidate=matched, **decided)
        elif chosen in KINDS:
            upto = session.heard[:position(session.heard, heard) + 1]
            language = card_language(upto, heard, self.sessions.config.card_language)
            candidate = Candidate(f"C{len(session.candidates) + 1}", chosen, heard, probability, language)
            session.candidates.append(candidate)
            session.log("candidate", **candidate.event())
            session.log("decision", outcome="candidate", candidate=candidate.id, **decided)
        else:
            session.log("decision", outcome="none", **decided)

    async def place_and_time(self, session: Session) -> str:
        """The place name with the local date, time and timezone, from
        location when it is installed; otherwise the date, time and
        timezone only."""
        locator = self.sessions.locator
        if locator is not None:
            try:
                text = locator.place_and_time(session, with_place=True)
                return await text if inspect.isawaitable(text) else text
            except Exception:
                log.exception("session %s: no place from location; the date and time only", session.id)
        return date_time(session.timezone)

    async def account(self, session: Session, heard: Heard, question: Question, record: CallRecord) -> None:
        """Record the call and charge its cost, an estimate included.

        The recording keeps the prompt's name and version with the values
        filled in and the choices offered, not the rendered request: a replay
        rebuilds it from these.
        """
        event = record.event()
        event.pop("request", None)
        session.log("model call", utterance=heard.id, choices=list(question.choices), **event)
        session.cost_usd += record.charged_usd
        try:
            await self.sessions.costs.charge(STAGE, record.provider, self.sessions.config.stages.decision.model,
                                             record.charged_usd, estimated=record.estimated, when=record.started_at)
        except Exception:  # noqa: BLE001 - a cost that can't be written is logged, never fatal
            log.exception("session %s: couldn't write a charge of $%.6f", session.id, record.charged_usd)


def install(sessions: Sessions, environ: Mapping[str, str]) -> None:
    """Plug the decision call into the sessions (`sessions.decider`).

    The model is the config's `stages.decision`, its key from `environ`.
    Without the key, Carl runs with no decision calls, so a local run still
    works.
    """
    stage, config = sessions.config.stages.decision, sessions.config
    key = {"openai": "OPENAI_API_KEY", "openrouter": "OPENROUTER_API_KEY"}.get(stage.provider)
    if key is not None and not environ.get(key):
        log.warning("no decision calls: %s isn't set", key)
        return
    # The provider and its parameters are checked now, and a mistake stops
    # startup. The model itself is made on its first call, inside the event loop.
    make_typed_model(stage, config, environ, None)
    sessions.decider = Decider(sessions, LazyModel(lambda: make_typed_model(stage, config, environ, http_session())))
