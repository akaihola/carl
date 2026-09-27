"""A candidate's check (spec sections 5, 6 and 8): from the decision call's
candidate to a fact card on the page, or to silence.

Each candidate is its own task, started when the decision call flags it
(`Checker.start`), with no queue: a slow check never holds up another, and
End waits for it (`Session.spawn_check`). Its state (`Candidate.state`):

- `finding`: fact-finder B searches and writes a draft card. Its restatement
  goes onto the candidate as soon as it arrives, so later decision calls list
  the candidate by it rather than by the raw utterance.
- `checking`: the draft card's source against the blocklist, its excerpt
  against B's search-result snippets, then the verdict.
- `ready`: the card was sent to the page, or waits in the session for the
  page to rejoin. The page's reports move it on to `on screen` and `card
  history` (`carl.session.Card`).
- `silent`: no card, for the band's reason code (`claim is right`, `not
  found`, a blocklisted source, an unverified excerpt, a verdict that isn't
  `supported` or is below the hedged bar).
- `failed`: a typed error from fact-finder B or the verdict call. The failure
  log comes with step 7.
- `dropped`: the session ended first, so no card is sent. A candidate flagged
  after End is dropped before any search.

**What each model gets.** B gets the candidate's kind, its line, the decision
call's context window (`carl.decision.context`), the place name with the
local date, time and timezone, the card language by name, and its search
tool's `user_location` as place names. The verdict gets the candidate's line
and the same window, the draft card's title and fact, its excerpt, and the
local date and time: never the restatement, so a fact-finder's misreading
can't vouch for itself, and never the source's URL or title.

**Rate limits.** Perplexity refused requests sent at once with 429 (ticket
30). A `rate-limited` finding is tried once more after `RETRY_AFTER_S` if the
candidate is still young (`RETRY_YOUNG_S` since its utterance ended). The
adapters never retry; this is the pipeline's choice. Any other error, or a
second 429, fails the candidate.

**The verdict is skipped** for a card whose source is blocklisted or whose
excerpt isn't verified: judged alone, such a card is silent whatever the
verdict says, so the call and its time are saved. The recording says why
(`verdict skipped` with the reason code). Step 5 asks it for every card of a
pair, since the other card of an agreeing pair may be unverified.

**Costs.** Every call, a failed one included (an estimate if its usage is
unknown), is charged to the month as `fact-finding B` or `fact-checking` and
added to the session's cost. Perplexity's and OpenRouter's own figures count
when they give one (`CallRecord.charged_usd`); the record keeps both.

**The recording**, for each candidate: each model call with its record
(without the rendered request, which the prompt's name, version and fields
rebuild) and, for B, the `user_location` its search tool got and the attempt;
the `finding` (outcome, restatement, draft card, searches, results with their
snippets, the model B ran); the `excerpt` match; any `blocklisted` source;
the `verdict` with its probabilities or why it was skipped; the `band` with
its reason code; every `card sent`; and a closing `check` event with the
candidate's state and the seconds since its utterance ended. The card
language is on the `candidate` event. The languages of the card and the
excerpt aren't worked out here: both texts are in the recording, so the
corpus tools (step 8) can tell them.

Step 5 adds fact-finder A beside B, the wait for both, A's page download, the
agreement call and `band_pair`: `judge` already runs one fact-finder's part
and returns a `Part` the bands can read.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .checking import SUPPORTED, Band, Judged, band_single, blocklisted, card_words, hedged_fact, snippet_match
from .decision import Candidate, LazyModel, context, line, position
from .finding import (
    STAGE_B, DraftCard, FactFinder, Finding, FindingRequest, key_name, language_name, make_fact_finder,
    perplexity_location,
)
from .location import date_time
from .models import CallRecord, ModelError, TypedAnswer, TypedModel, http_session, make_typed_model
from .models.questions import TypedPrompt
from .session import Card, Heard, Session, Sessions, iso_time

log = logging.getLogger(__name__)

STAGE = "fact-checking"
NOTHING_BEFORE = "(nothing said before)"
RETRY_AFTER_S = 1.5
# Young enough for one more try: a card can then still reach the screen
# before the late-card cut-off, 20 s after the utterance.
RETRY_YOUNG_S = 10.0
# The card's `kind` on the page.
KINDS = {"claim": "claim", "open question": "question"}
# For a candidate none of whose words had a language code: Carl's own language.
FALLBACK_LANGUAGE = "en"
TYPED_KEYS = {"openai": "OPENAI_API_KEY", "openrouter": "OPENROUTER_API_KEY"}


def window(session: Session, heard: Heard) -> list[str]:
    """The lines of the decision call's context window for `heard`, oldest first."""
    s = session.config.decision
    before = session.heard[:position(session.heard, heard)]
    return [line(item) for item in context(before, heard, s.context_utterances, s.context_window_s)]


def verdict_fields(candidate: str, conversation: Sequence[str], card: DraftCard, when: str) -> dict[str, str]:
    """The verdict's named text fields: never the restatement, the source's
    URL or its title."""
    return {
        "date_time": when,
        "conversation": "\n".join(conversation) or NOTHING_BEFORE,
        "candidate": candidate,
        "card_title": card.title,
        "card_fact": card.fact,
        "excerpt": card.excerpt,
    }


def card_content(candidate: Candidate, band: Band, draft: DraftCard, language: str) -> dict[str, Any]:
    """The `card` message's card (docs/websocket.md), `age_s` aside: the
    label, the hedged tag and the hedge prefix in the card language, the
    title and fact as the fact-finder wrote them."""
    words = card_words(candidate.kind, band.band, language)
    return {
        "id": candidate.id, "kind": KINDS[candidate.kind], "band": band.band, "language": language,
        "label": words["label"], "tag": words["tag"], "title": draft.title,
        "fact": hedged_fact(draft.fact, words["prefix"]),
        "source": {"url": draft.source_url, "title": draft.source_title},
        "utterance_time": iso_time(candidate.heard.time),
    }


@dataclass
class Part:
    """One fact-finder's part of a check: its finding, and for a draft card
    the blocklist, the excerpt match and the verdict (or the verdict call's
    error)."""

    finder: str  # A or B
    finding: Finding
    verified: bool = False
    blocklisted: str | None = None
    verdict: TypedAnswer | None = None
    error: ModelError | None = None

    def judged(self) -> Judged:
        """As the bands see it."""
        probs = None if self.verdict is None else self.verdict.probs
        return Judged(self.finder, self.finding.outcome, self.verified, self.blocklisted,
                      None if self.verdict is None else self.verdict.answer,
                      None if probs is None else probs.get(SUPPORTED, 0.0))


class LazyFinder:
    """A fact-finder made on its first call: its HTTP session needs the running event loop."""

    def __init__(self, make: Callable[[], FactFinder]) -> None:
        self.make = make
        self.finder: FactFinder | None = None

    async def find(self, request: FindingRequest, *, stage: str) -> Finding:
        if self.finder is None:
            self.finder = self.make()
        return await self.finder.find(request, stage=stage)


class Checker:
    """Every session's candidates' checks: `sessions.checker`."""

    def __init__(self, sessions: Sessions, finder: FactFinder, model: TypedModel) -> None:
        self.sessions, self.finder, self.model = sessions, finder, model
        self.finding_prompt = sessions.prompts["fact-finding"]
        self.prompt = TypedPrompt.load(sessions.prompts["fact-checking"])
        stages = sessions.config.stages
        self.models = {STAGE_B: stages.fact_finder_b.model, STAGE: stages.fact_checking.model}

    def start(self, session: Session, candidate: Candidate) -> asyncio.Task:
        """Start the candidate's check as its own task, which End waits for."""
        candidate.state = "finding"
        return session.spawn_check(self.check(session, candidate))

    async def check(self, session: Session, candidate: Candidate) -> None:
        try:
            await self.run(session, candidate)
        except Exception:
            log.exception("session %s: the check of %s went wrong", session.id, candidate.id)
            self.finish(session, candidate, "failed", stage="checks", error="bug")

    async def run(self, session: Session, candidate: Candidate) -> None:
        if session.state == "ended":
            self.finish(session, candidate, "dropped", reason="session ended")
            return
        conversation = window(session, candidate.heard)
        try:
            finding = await self.find(session, candidate, self.request(session, candidate, conversation))
        except ModelError as e:
            log.warning("session %s: %s; %s failed", session.id, e, candidate.id)
            self.finish(session, candidate, "failed", stage=e.record.stage, error=e.kind)
            return
        if candidate.restatement is None:
            candidate.restatement = finding.restatement
        session.log("finding", candidate=candidate.id, finder="B", **finding.event())
        candidate.state = "checking"
        part = await self.judge(session, candidate, "B", finding, conversation)
        band = band_single(part.judged(), self.sessions.config.bands)
        session.log("band", candidate=candidate.id, band=band.band, reason=band.reason, shown=band.shown)
        draft = part.finding.card
        if part.error is not None:
            self.finish(session, candidate, "failed", stage=STAGE, error=part.error.kind)
        elif band.band == "none" or draft is None:
            self.finish(session, candidate, "silent", reason=band.reason)
        elif session.state == "ended":
            self.finish(session, candidate, "dropped", reason="session ended", band=band.band)
        else:
            content = card_content(candidate, band, draft, self.language(candidate))
            self.finish(session, candidate, "ready", band=band.band, reason=band.reason)
            await session.send_card(Card(candidate.id, content, candidate.heard.time, candidate))

    def request(self, session: Session, candidate: Candidate, conversation: Sequence[str]) -> FindingRequest:
        """What the fact-finders are given: the same for both."""
        locator = self.sessions.locator
        where, openai, perplexity = date_time(session.timezone), None, None
        if locator is not None:
            try:
                where = locator.place_and_time(session, with_place=True)
                openai, perplexity = locator.openai_user_location(session), locator.perplexity_user_location(session)
            except Exception:
                log.exception("session %s: no place from location; the date and time only", session.id)
        return FindingRequest(self.finding_prompt, candidate.kind, line(candidate.heard), conversation, where,
                              language_name(self.language(candidate)), openai, perplexity)

    @staticmethod
    def language(candidate: Candidate) -> str:
        return candidate.card_language.language or FALLBACK_LANGUAGE

    async def find(self, session: Session, candidate: Candidate, request: FindingRequest) -> Finding:
        """Fact-finder B's finding, tried once more after a 429 while the
        candidate is young. Every call is recorded and charged. Raises
        ModelError."""
        where = perplexity_location(request.perplexity_location)
        attempt = 1
        while True:
            try:
                finding = await self.finder.find(request, stage=STAGE_B)
            except ModelError as e:
                await self.account(session, candidate, e.record, finder="B", attempt=attempt, user_location=where)
                if e.kind == "rate-limited" and attempt == 1 and time.time() - candidate.heard.time < RETRY_YOUNG_S:
                    log.info("session %s: %s; trying %s once more", session.id, e, candidate.id)
                    attempt += 1
                    await asyncio.sleep(RETRY_AFTER_S)
                    continue
                raise
            await self.account(session, candidate, finding.record, finder="B", attempt=attempt, user_location=where)
            return finding

    async def judge(self, session: Session, candidate: Candidate, finder: str, finding: Finding,
                    conversation: Sequence[str]) -> Part:
        """One fact-finder's draft card: the blocklist, the excerpt match and,
        for a card that could be shown, the verdict. A finding without a card
        is its outcome alone."""
        part, draft = Part(finder, finding), finding.card
        if draft is None:
            return part
        part.blocklisted = blocklisted(draft.source_url, self.sessions.config.sources.blocklist)
        if part.blocklisted is not None:
            session.log("blocklisted", candidate=candidate.id, finder=finder, url=draft.source_url,
                        suffix=part.blocklisted)
        part.verified = snippet_match(draft.excerpt, draft.source_url, finding.results)  # A's download: step 5
        session.log("excerpt", candidate=candidate.id, finder=finder, method="snippet", verified=part.verified)
        if part.blocklisted is not None or not part.verified:
            reason = "silent:blocklisted" if part.blocklisted is not None else "silent:unverified"
            session.log("verdict skipped", candidate=candidate.id, finder=finder, reason=reason)
            return part
        question = self.prompt.fill(verdict_fields(line(candidate.heard), conversation, draft,
                                                   date_time(session.timezone)))
        try:
            part.verdict = await self.model.ask(question, stage=STAGE)
        except ModelError as e:
            part.error = e
            await self.account(session, candidate, e.record, finder=finder)
            session.log("verdict", candidate=candidate.id, finder=finder, answer=None, probs=None, error=e.kind)
            log.warning("session %s: %s; %s failed", session.id, e, candidate.id)
            return part
        await self.account(session, candidate, part.verdict.record, finder=finder)
        session.log("verdict", candidate=candidate.id, finder=finder, answer=part.verdict.answer,
                    probs=part.verdict.probs)
        return part

    async def account(self, session: Session, candidate: Candidate, record: CallRecord, **fields: Any) -> None:
        """Record the call and charge its cost, an estimate included, to the
        month and the session."""
        event = record.event()
        event.pop("request", None)
        session.log("model call", candidate=candidate.id, utterance=candidate.heard.id, **fields, **event)
        session.cost_usd += record.charged_usd
        try:
            await self.sessions.costs.charge(record.stage, record.provider, self.models[record.stage],
                                             record.charged_usd, estimated=record.estimated,
                                             when=record.started_at)
        except Exception:  # noqa: BLE001 - a cost that can't be written is logged, never fatal
            log.exception("session %s: couldn't write a charge of $%.6f", session.id, record.charged_usd)

    @staticmethod
    def finish(session: Session, candidate: Candidate, state: str, **fields: Any) -> None:
        candidate.state = state
        session.log("check", candidate=candidate.id, state=state,
                    after_s=round(time.time() - candidate.heard.time, 1), **fields)


def install(sessions: Sessions, environ: Mapping[str, str]) -> None:
    """Plug the candidates' checks into the sessions (`sessions.checker`):
    fact-finder B (`stages.fact_finder_b`) and the fact-checking model
    (`stages.fact_checking`), their keys from `environ`.

    Without a key, Carl runs with no checks, so a local run still works. A
    mistake in either stage stops startup.
    """
    config = sessions.config
    finding, checking = config.stages.fact_finder_b, config.stages.fact_checking
    keys = [key_name(finding), TYPED_KEYS.get(checking.provider)]
    missing = [k for k in keys if k is not None and not environ.get(k)]
    if missing:
        log.warning("no checks: %s not set", " and ".join(missing))
        return
    # Checked now; each is made on its first call, inside the event loop.
    make_fact_finder(finding, config, environ, None)  # type: ignore[arg-type]
    make_typed_model(checking, config, environ, None)  # type: ignore[arg-type]
    sessions.checker = Checker(
        sessions,
        LazyFinder(lambda: make_fact_finder(finding, config, environ, http_session())),
        LazyModel(lambda: make_typed_model(checking, config, environ, http_session())),
    )
