"""A candidate's check (spec sections 5, 6 and 8): from the decision call's
candidate to a fact card on the page, or to silence.

Each candidate is its own task, started when the decision call flags it
(`Checker.start`), with no queue: a slow check never holds up another, and
End waits for it (`Session.spawn_check`). Its state (`Candidate.state`):

- `finding`: both fact-finders search and write their draft cards. The first
  restatement to arrive goes onto the candidate at once, so later decision
  calls list the candidate by it rather than by the raw utterance.
- `checking`: the verdicts and the agreement call.
- `ready`: the card was sent to the page, or waits in the session for the
  page to rejoin. The page's reports move it on to `on screen` and `card
  history` (`carl.session.Card`).
- `silent`: no card, for the band's reason code.
- `failed`: both fact-finders failed, or a failed verdict or agreement call
  left the band with nothing (`silent:no-verdict`, `silent:no-agreement`);
  or `overload`: `candidates.max_live` candidates were already live when it
  was flagged; or the candidate timeout: it was still being checked
  `candidates.timeout_s` after its utterance ended, and has failed against
  the stages it was waiting on. One fact-finder failing while the other works
  doesn't fail the candidate. A repeat of a failed candidate is checked as a
  new one (`carl.decision`). Every failure goes to `Session.failure`, and
  each candidate's outcome at fact-finding and fact-checking to the
  indicator's "Can't check" (`carl.outages`); `overload` counts for nothing.
- `dropped`: settled at the table before its card was on screen
  (`silent:settled`, `carl.settle`), a card already sent withdrawn; flagged
  in an utterance that disputes the card on screen, which already answers it
  (`silent:disputing`); or the session ended first, so no card is sent (a
  candidate flagged after End is dropped before any search).

A timed-out or dropped candidate's calls in flight aren't cancelled: they
finish, are recorded and charged, and their results are thrown away.

**Both fact-finders** (`Checker.finders`, A and B; either may be off, which
allows hedged cards only) get the same prompt and the same input at once:
the candidate's kind, its line, the decision call's context window
(`carl.decision.context`), the place name with the local date, time and
timezone, the card language by name, and each its own search tool's
`user_location` as place names. Each runs as its own task, which End waits
for: a fact-finder's part is its finding, recorded as it arrives, and its
draft card's source and excerpt checked.

**Waiting for both.** Once the first part is ready, Carl waits
`candidates.second_finder_wait_s` for the other. One that fails or misses
the wait leaves the other's card to be judged alone; a missed one still
finishes in the background, so it is recorded and charged, but it changes
nothing. A card is never shown first and then confirmed or withdrawn. A's
part includes its page download (at most `source_download_timeout_s`), so
the wait may count from a little after A's outcome arrived.

**Matching excerpts.** A Perplexity fact-finder's excerpt must be in a
search-result snippet from the same page (`snippet_match`); an OpenAI one's
source page is downloaded (`page_match`, one `download_client` per checker,
closed at shutdown) and searched. Each download is recorded as a call
costing 0. A blocklisted source is never downloaded: its card can't be
shown, and the other card of an agreeing pair needs no verified excerpt.

**Verdicts and the agreement call** go to the fact-checking model at once.
A card's verdict is asked only when it can matter (`needs_verdict`): a card
that could be shown (a verified excerpt from a source that isn't
blocklisted), or the other card of a pair with the same outcome, whose
p(supported) the plain band needs; never for a card that a contradiction or
mixed outcomes leave silent. The recording says why one is skipped. The
verdict gets the candidate's line and its window, the card's title and fact,
its excerpt and the local date and time; the agreement call, for two cards
with the same outcome, gets the candidate's line, both cards (title and
fact) and the date and time. Neither gets a restatement, so a fact-finder's
misreading can't vouch for itself, nor a source's URL or title. Nothing is
translated. `band_pair` then gives the band: plain, hedged or nothing.

**Rate limits.** Perplexity refused requests sent at once with 429 (ticket
30). A `rate-limited` finding is tried once more after `RETRY_AFTER_S` if the
candidate is still young (`RETRY_YOUNG_S` since its utterance ended). The
adapters never retry; this is the pipeline's choice.

**Costs.** Every call, a failed one included (an estimate if its usage is
unknown), is charged to the month as `fact-finding A`, `fact-finding B` or
`fact-checking` (verdicts and the agreement call) and added to the session's
cost. Perplexity's and OpenRouter's own figures count when they give one
(`CallRecord.charged_usd`); the record keeps both.

**The recording**, for each candidate: each model call with its record
(without the rendered request, which the prompt's name, version and fields
rebuild), a fact-finder's with the `user_location` its search tool got and
the attempt; each `finding` (outcome, restatement, draft card, searches,
results with any snippets, the model that ran, seconds since the utterance);
`findings`, which fact-finders were used, failed or missed the wait; each
`download` and `excerpt` match; any `blocklisted` source; each `verdict`
with its probabilities or why it was skipped; the `agreement`; the `band`
with its reason code; every `card sent`; and a closing `check` event with
the candidate's state and the seconds since its utterance ended. The card
language is on the `candidate` event. The languages of the cards and the
excerpts aren't worked out here: the texts are in the recording, so the
corpus tools (step 8) can tell them.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import httpx

from .checking import (
    CLAIM_RIGHT, CLAIM_WRONG, NOT_FOUND, SAME_FACT, SUPPORTED, Agreement, Band, Judged, PageMatch, band_pair,
    blocklisted, card_words, download_client, hedged_fact, page_match, snippet_match,
)
from .decision import Candidate, LazyModel, context, line, position
from .finding import (
    STAGE_A, STAGE_B, DraftCard, FactFinder, Finding, FindingRequest, key_name, language_name, make_fact_finder,
    openai_location, perplexity_location,
)
from .location import date_time
from .models import CallRecord, ModelError, TypedAnswer, TypedModel, http_session, make_typed_model
from .models.questions import TypedPrompt
from .session import Card, Heard, Session, Sessions, iso_time

log = logging.getLogger(__name__)

STAGE = "fact-checking"
STAGES = {"A": STAGE_A, "B": STAGE_B}
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
# The silent bands a failed fact-checking call can cause: the candidate failed.
CALL_FAILED = ("silent:no-verdict", "silent:no-agreement")
# The states in which a candidate is still being checked.
CHECKING = ("finding", "checking")


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


def card_line(card: DraftCard) -> str:
    """A card as the agreement call sees it: `title: fact`."""
    return f"{card.title}: {card.fact}"


def agreement_fields(candidate: str, card_1: str, card_2: str, when: str) -> dict[str, str]:
    """The agreement call's named text fields: the candidate's line and both
    cards (`card_line`), never a restatement, an excerpt or a source."""
    return {"date_time": when, "candidate": candidate, "card_1": card_1, "card_2": card_2}


def card_content(candidate: Candidate, band: Band, draft: DraftCard, language: str) -> dict[str, Any]:
    """The `card` message's card (docs/websocket.md), `age_s` aside: the
    label, and on a hedged card the tag and the hedge prefix, in the card
    language; the title and fact as the fact-finder wrote them."""
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

    @property
    def card(self) -> DraftCard | None:
        return self.finding.card

    @property
    def showable(self) -> bool:
        """It could be shown judged alone, the verdict aside: a verified
        excerpt from a source that isn't blocklisted."""
        return self.card is not None and self.verified and self.blocklisted is None

    def judged(self) -> Judged:
        """As the bands see it."""
        probs = None if self.verdict is None else self.verdict.probs
        return Judged(self.finder, self.finding.outcome, self.verified, self.blocklisted,
                      None if self.verdict is None else self.verdict.answer,
                      None if probs is None else probs.get(SUPPORTED, 0.0))


def same_outcome_cards(a: Part | None, b: Part | None) -> bool:
    """Two draft cards with the same outcome: the agreement call decides."""
    return (a is not None and b is not None and a.card is not None and b.card is not None
            and a.finding.outcome == b.finding.outcome)


def needs_verdict(part: Part, other: Part | None) -> bool:
    """Whether `part`'s verdict can change the band, given `other`, the other
    fact-finder's part (None when it is off, failed or missed the wait).

    - Judged alone (no other, or the other found nothing): only a card that
      could be shown.
    - Two cards with the same outcome: either card, if at least one could be
      shown, since the plain band needs the other card's p(supported) too.
    - A contradiction or mixed outcomes show nothing: neither.
    """
    if part.card is None:
        return False
    if other is None or other.finding.outcome == NOT_FOUND:
        return part.showable
    if same_outcome_cards(part, other):
        return part.showable or other.showable
    return False


def skipped_because(part: Part, other: Part | None) -> str:
    """The reason code for a verdict `needs_verdict` skips."""
    if not part.showable:
        return "silent:blocklisted" if part.blocklisted is not None else "silent:unverified"
    outcomes = {part.finding.outcome, other.finding.outcome if other else None}
    return "silent:contradiction" if outcomes == {CLAIM_WRONG, CLAIM_RIGHT} else "silent:mixed-outcomes"


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
    """Every session's candidates' checks: `sessions.checker`.

    `finders` maps `A` and `B` to their fact-finders; one alone allows
    hedged cards only.
    """

    def __init__(self, sessions: Sessions, finders: Mapping[str, FactFinder], model: TypedModel) -> None:
        if not finders or not finders.keys() <= STAGES.keys():
            raise ValueError(f"the fact-finders are A and B, not {sorted(finders)}")
        self.sessions, self.finders, self.model = sessions, dict(finders), model
        self.finding_prompt = sessions.prompts["fact-finding"]
        self.verdict_prompt = TypedPrompt.load(sessions.prompts["fact-checking"])
        self.agreement_prompt = TypedPrompt.load(sessions.prompts["same-fact"])
        stages = sessions.config.stages
        self.stages = {"A": stages.fact_finder_a, "B": stages.fact_finder_b}
        self.configs = {STAGE_A: stages.fact_finder_a, STAGE_B: stages.fact_finder_b, STAGE: stages.fact_checking}
        self.downloads: httpx.AsyncClient | None = None

    def start(self, session: Session, candidate: Candidate) -> asyncio.Task | None:
        """Start the candidate's check as its own task, which End waits for;
        or drop it, flagged in an utterance that disputes the card on screen;
        or fail it with `overload` when `max_live` candidates are live."""
        if (disputed := session.disputing.get(candidate.heard.id)) is not None:
            self.finish(session, candidate, "dropped", reason="silent:disputing", disputes=disputed)
            return None
        live = sum(c.live for c in session.candidates if c is not candidate)
        if live >= self.sessions.config.candidates.max_live:
            log.warning("session %s: %d candidates live; %s fails with overload", session.id, live, candidate.id)
            session.failure("fact-finding", "overload", candidate=candidate.id, live=live)
            self.finish(session, candidate, "failed", stage="fact-finding", kind="overload")
            return None
        candidate.state = "finding"
        return session.spawn_check(self.check(session, candidate))

    async def drop(self, session: Session, candidate: Candidate, reason: str, **fields: Any) -> bool:
        """Drop a live candidate whose card isn't on screen yet: its check's
        results are thrown away, and a card already sent is withdrawn. The
        recording keeps the band as `reason` (`silent:settled`). False when
        it is too late: the card is on screen, or the candidate isn't live."""
        was = candidate.state
        if was not in (*CHECKING, "ready"):
            return False
        session.log("band", candidate=candidate.id, band="none", reason=reason, shown=None, **fields)
        self.finish(session, candidate, "dropped", reason=reason, **fields)
        if was == "ready":
            await session.withdraw_card(candidate.id, reason=reason)
        return True

    def expire(self, session: Session, candidate: Candidate) -> None:
        """The candidate timeout: a candidate still being checked has failed,
        against each stage it was waiting on."""
        if candidate.state not in CHECKING:
            return
        stage = "fact-finding" if candidate.state == "finding" else STAGE
        stages = sorted(candidate.waiting_on) or [stage]
        log.warning("session %s: %s timed out in %s", session.id, candidate.id, ", ".join(stages))
        for name in stages:
            config = self.configs.get(name)
            session.failure(name, "timeout", candidate=candidate.id, provider=config and config.provider,
                            model=config and config.model)
        self.finish(session, candidate, "failed", stage=stage, kind="timeout", waiting_on=stages)
        session.health.candidate(stage, False)  # a failure of the stage it was stuck in

    async def close(self) -> None:
        """At shutdown: close the source-page downloads' client."""
        if self.downloads is not None:
            await self.downloads.aclose()
            self.downloads = None

    async def check(self, session: Session, candidate: Candidate) -> None:
        loop = asyncio.get_running_loop()
        left = candidate.heard.time + self.sessions.config.candidates.timeout_s - time.time()
        timer = loop.call_later(max(0.0, left), self.expire, session, candidate)
        try:
            await self.run(session, candidate)
        except Exception:
            log.exception("session %s: the check of %s went wrong", session.id, candidate.id)
            if candidate.state in CHECKING:
                self.finish(session, candidate, "failed", stage="checks", errors={"check": "bug"})
        finally:
            timer.cancel()

    async def run(self, session: Session, candidate: Candidate) -> None:
        if session.state == "ended":
            self.finish(session, candidate, "dropped", reason="session ended")
            return
        conversation = window(session, candidate.heard)
        parts, failed, missed = await self.gather(session, candidate,
                                                  self.request(session, candidate, conversation))
        session.log("findings", candidate=candidate.id, used=list(parts), failed=failed, missed=missed)
        if candidate.state != "finding":  # dropped or timed out meanwhile: the findings are thrown away
            return
        session.health.candidate("fact-finding", bool(parts))
        if not parts:
            self.finish(session, candidate, "failed", stage="fact-finding", errors=failed)
            return
        candidate.state, candidate.waiting_on = "checking", {STAGE}
        a, b = parts.get("A"), parts.get("B")
        agreement, agreement_error = await self.judge(session, candidate, a, b, conversation)
        candidate.waiting_on = set()
        if candidate.state != "checking":  # dropped or timed out meanwhile: the verdicts are thrown away
            return
        band = band_pair(a and a.judged(), b and b.judged(), agreement, self.sessions.config.bands)
        called = agreement is not None or agreement_error is not None or any(
            p.verdict is not None or p.error is not None for p in parts.values())
        if called:  # the stage fails for a candidate only when a failed call leaves it without a band
            session.health.candidate(STAGE, band.reason not in CALL_FAILED)
        session.log("band", candidate=candidate.id, band=band.band, reason=band.reason, shown=band.shown)
        if band.shown is not None and (draft := parts[band.shown].card) is not None:
            if session.state == "ended":
                self.finish(session, candidate, "dropped", reason="session ended", band=band.band)
                return
            content = card_content(candidate, band, draft, self.language(candidate))
            self.finish(session, candidate, "ready", band=band.band, reason=band.reason)
            await session.send_card(Card(candidate.id, content, candidate.heard.time, candidate))
        elif band.reason in CALL_FAILED:
            errors = {p.finder: p.error.kind for p in parts.values() if p.error is not None}
            if agreement_error is not None:
                errors["agreement"] = agreement_error
            self.finish(session, candidate, "failed", stage=STAGE, reason=band.reason, errors=errors)
        else:
            self.finish(session, candidate, "silent", reason=band.reason)

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

    # --- Finding ---------------------------------------------------------------------------

    async def gather(self, session: Session, candidate: Candidate,
                     request: FindingRequest) -> tuple[dict[str, Part], dict[str, str], list[str]]:
        """Every fact-finder at once, each as its own task. Returns the parts
        ready by `second_finder_wait_s` after the first, in the order they
        arrived; the typed error of each that failed; and those that missed
        the wait, which carry on in the background."""
        loop = asyncio.get_running_loop()
        wait_s = self.sessions.config.candidates.second_finder_wait_s
        candidate.waiting_on = {STAGES[letter] for letter in self.finders}
        tasks = {session.spawn_check(self.part(session, candidate, letter, request)): letter
                 for letter in self.finders}
        parts: dict[str, Part] = {}
        failed: dict[str, str] = {}
        pending, deadline = set(tasks), None
        while pending:
            timeout = None if deadline is None else deadline - loop.time()
            if timeout is not None and timeout <= 0:
                break
            done, pending = await asyncio.wait(pending, timeout=timeout, return_when=asyncio.FIRST_COMPLETED)
            for task in sorted(done, key=lambda t: tasks[t]):
                result = task.result()
                if isinstance(result, Part):
                    parts[tasks[task]] = result
                    if deadline is None:
                        deadline = loop.time() + wait_s
                else:
                    failed[tasks[task]] = result
        missed = sorted(tasks[task] for task in pending)
        candidate.waiting_on = set()
        if missed:
            log.info("session %s: %s goes on without fact-finder %s", session.id, candidate.id, ", ".join(missed))
        return parts, failed, missed

    async def part(self, session: Session, candidate: Candidate, letter: str, request: FindingRequest) -> Part | str:
        """One fact-finder's part: its finding, recorded as it arrives, and
        its draft card's source and excerpt checked. A typed error's kind
        when it failed."""
        try:
            finding = await self.find(session, candidate, letter, request)
            if candidate.restatement is None:  # the first to arrive
                candidate.restatement = finding.restatement
            session.log("finding", candidate=candidate.id, finder=letter,
                        after_s=round(time.time() - candidate.heard.time, 1), **finding.event())
            return await self.match(session, candidate, Part(letter, finding))
        except ModelError as e:
            log.warning("session %s: %s; %s goes on without it", session.id, e, candidate.id)
            return e.kind
        except Exception:
            log.exception("session %s: fact-finder %s on %s went wrong", session.id, letter, candidate.id)
            return "bug"
        finally:
            candidate.waiting_on.discard(STAGES[letter])

    async def find(self, session: Session, candidate: Candidate, letter: str, request: FindingRequest) -> Finding:
        """One fact-finder's finding, tried once more after a 429 while the
        candidate is young. Every call is recorded and charged. Raises
        ModelError."""
        if self.stages[letter].provider == "perplexity":
            where = perplexity_location(request.perplexity_location)
        else:
            where = openai_location(request.openai_location)
        attempt = 1
        while True:
            try:
                finding = await self.finders[letter].find(request, stage=STAGES[letter])
            except ModelError as e:
                await self.account(session, candidate, e.record, finder=letter, attempt=attempt,
                                   user_location=where)
                session.failure(STAGES[letter], e.kind, record=e.record, candidate=candidate.id)
                if e.kind == "rate-limited" and attempt == 1 and time.time() - candidate.heard.time < RETRY_YOUNG_S:
                    log.info("session %s: %s; trying %s once more", session.id, e, candidate.id)
                    attempt += 1
                    await asyncio.sleep(RETRY_AFTER_S)
                    continue
                raise
            await self.account(session, candidate, finding.record, finder=letter, attempt=attempt,
                               user_location=where)
            return finding

    async def match(self, session: Session, candidate: Candidate, part: Part) -> Part:
        """The draft card's source against the blocklist, and its excerpt
        against the search-result snippets (Perplexity) or the downloaded
        page (OpenAI, unless the source is blocklisted)."""
        draft = part.card
        if draft is None:
            return part
        part.blocklisted = blocklisted(draft.source_url, self.sessions.config.sources.blocklist)
        if part.blocklisted is not None:
            session.log("blocklisted", candidate=candidate.id, finder=part.finder, url=draft.source_url,
                        suffix=part.blocklisted)
        fields: dict[str, Any] = {"candidate": candidate.id, "finder": part.finder}
        if self.stages[part.finder].provider == "perplexity":
            part.verified = snippet_match(draft.excerpt, draft.source_url, part.finding.results)
            session.log("excerpt", **fields, method="snippet", verified=part.verified)
        elif part.blocklisted is not None:
            session.log("excerpt", **fields, method="page", verified=False, reason="blocklisted")
        else:
            page = await self.download(session, candidate, part.finder, draft)
            part.verified = page.verified
            session.log("excerpt", **fields, method="page", verified=page.verified, reason=page.reason,
                        match=page.match)
        return part

    async def download(self, session: Session, candidate: Candidate, finder: str, draft: DraftCard) -> PageMatch:
        """The card's source page, searched for its excerpt; recorded as a call costing 0."""
        if self.downloads is None:
            self.downloads = download_client()
        page = await page_match(draft.excerpt, draft.source_url,
                                self.sessions.config.candidates.source_download_timeout_s, client=self.downloads)
        session.log("download", candidate=candidate.id, finder=finder, stage=STAGES[finder], url=draft.source_url,
                    cost_usd=0.0, **page.event())
        return page

    # --- Fact-checking ----------------------------------------------------------------------

    async def judge(self, session: Session, candidate: Candidate, a: Part | None, b: Part | None,
                    conversation: Sequence[str]) -> tuple[Agreement | None, str | None]:
        """The verdicts that can matter and, for two cards with the same
        outcome, the agreement call, all at once. Returns the agreement, and
        the agreement call's typed error if it failed."""
        calls = []
        for part, other in ((a, b), (b, a)):
            if part is None or part.card is None:
                continue
            if needs_verdict(part, other):
                calls.append(self.verdict(session, candidate, part, conversation))
            else:
                session.log("verdict skipped", candidate=candidate.id, finder=part.finder,
                            reason=skipped_because(part, other))
        if not same_outcome_cards(a, b):
            await asyncio.gather(*calls)
            return None, None
        *_, agreed = await asyncio.gather(*calls, self.agree(session, candidate, a, b))  # type: ignore[arg-type]
        return agreed

    async def verdict(self, session: Session, candidate: Candidate, part: Part, conversation: Sequence[str]) -> None:
        """One draft card's verdict, onto `part`: its answer, or its error."""
        assert part.card is not None
        question = self.verdict_prompt.fill(verdict_fields(line(candidate.heard), conversation, part.card,
                                                           date_time(session.timezone)))
        fields = {"candidate": candidate.id, "finder": part.finder}
        try:
            part.verdict = await self.model.ask(question, stage=STAGE)
        except ModelError as e:
            part.error = e
            await self.account(session, candidate, e.record, finder=part.finder)
            session.failure(STAGE, e.kind, record=e.record, candidate=candidate.id)
            session.log("verdict", **fields, answer=None, probs=None, error=e.kind)
            log.warning("session %s: %s; no verdict on %s's card for %s", session.id, e, part.finder, candidate.id)
            return
        await self.account(session, candidate, part.verdict.record, finder=part.finder)
        session.log("verdict", **fields, answer=part.verdict.answer, probs=part.verdict.probs)

    async def agree(self, session: Session, candidate: Candidate, a: Part, b: Part) -> tuple[Agreement | None,
                                                                                               str | None]:
        """The agreement call on A's card (`card_1`) and B's (`card_2`)."""
        assert a.card is not None and b.card is not None
        question = self.agreement_prompt.fill(agreement_fields(line(candidate.heard), card_line(a.card),
                                                               card_line(b.card), date_time(session.timezone)))
        try:
            answer = await self.model.ask(question, stage=STAGE)
        except ModelError as e:
            await self.account(session, candidate, e.record)
            session.failure(STAGE, e.kind, record=e.record, candidate=candidate.id)
            session.log("agreement", candidate=candidate.id, answer=None, probs=None, error=e.kind)
            log.warning("session %s: %s; no agreement for %s", session.id, e, candidate.id)
            return None, e.kind
        await self.account(session, candidate, answer.record)
        session.log("agreement", candidate=candidate.id, answer=answer.answer, probs=answer.probs)
        return Agreement(answer.answer, None if answer.probs is None else answer.probs.get(SAME_FACT, 0.0)), None

    # --- Accounts ----------------------------------------------------------------------------

    async def account(self, session: Session, candidate: Candidate, record: CallRecord, **fields: Any) -> None:
        """Record the call and charge its cost, an estimate included, to the
        month and the session."""
        event = record.event()
        event.pop("request", None)
        session.log("model call", candidate=candidate.id, utterance=candidate.heard.id, **fields, **event)
        session.cost_usd += record.charged_usd
        try:
            await self.sessions.costs.charge(record.stage, record.provider, self.configs[record.stage].model,
                                             record.charged_usd, estimated=record.estimated,
                                             when=record.started_at)
        except Exception:  # noqa: BLE001 - a cost that can't be written is logged, never fatal
            log.exception("session %s: couldn't write a charge of $%.6f", session.id, record.charged_usd)

    @staticmethod
    def finish(session: Session, candidate: Candidate, state: str, **fields: Any) -> None:
        candidate.state = state
        session.save_soon()
        session.log("check", candidate=candidate.id, state=state,
                    after_s=round(time.time() - candidate.heard.time, 1), **fields)


def install(sessions: Sessions, environ: Mapping[str, str]) -> None:
    """Plug the candidates' checks into the sessions (`sessions.checker`):
    fact-finders A and B (`stages.fact_finder_a`, `stages.fact_finder_b`)
    and the fact-checking model (`stages.fact_checking`), their keys from
    `environ`.

    Without the fact-checking model's key, or without both fact-finders'
    keys, Carl runs with no checks, so a local run still works. With one
    fact-finder's key alone, it checks with that one, hedged cards only. A
    mistake in any of these stages stops startup.
    """
    config = sessions.config
    checking = config.stages.fact_checking
    stages = {"A": config.stages.fact_finder_a, "B": config.stages.fact_finder_b}
    keys = {letter: key_name(stage) for letter, stage in stages.items()}  # an unknown provider stops startup
    typed_key = TYPED_KEYS.get(checking.provider)
    if typed_key is not None and not environ.get(typed_key):
        log.warning("no checks: %s not set", typed_key)
        return
    on = {letter: stage for letter, stage in stages.items() if environ.get(keys[letter])}
    if not on:
        log.warning("no checks: %s not set", " and ".join(keys.values()))
        return
    for letter in sorted(stages.keys() - on.keys()):
        log.warning("fact-finder %s is off: %s not set; hedged cards only", letter, keys[letter])
    # Checked now; each is made on its first call, inside the event loop.
    for stage in on.values():
        make_fact_finder(stage, config, environ, None)  # type: ignore[arg-type]
    make_typed_model(checking, config, environ, None)  # type: ignore[arg-type]

    def lazy(stage):
        return LazyFinder(lambda: make_fact_finder(stage, config, environ, http_session()))

    sessions.checker = Checker(
        sessions, {letter: lazy(stage) for letter, stage in on.items()},
        LazyModel(lambda: make_typed_model(checking, config, environ, http_session())),
    )
