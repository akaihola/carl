import asyncio
import dataclasses
import json
import logging
import time

import pytest

from carl import checks
from carl.checks import Checker, LazyFinder, verdict_fields, window
from carl.decision import Candidate, Decider, LazyModel
from carl.finding import STAGE_B, DraftCard, Finding, SearchResult
from carl.language import card_language
from carl.location import Locator, Nominatim, Place
from carl.models import CallRecord, ModelError, TypedAnswer
from carl.prompts import load_prompts
from carl.server import SESSIONS
from carl.session import Card, Heard, Marker, Session, Sessions, iso_time
from carl.stt.fake import words
from carl.utterances import Utterance

from .conftest import ROOT
from .test_decision import Events
from .test_decision import FakeModel as DecisionModel
from .test_session import connect, events, receive, settle, start

FI_CARD = DraftCard(
    "Helsingin olympialaiset 1952", "Helsingin kesäolympialaiset pidettiin vuonna 1952, ei 1956.",
    "https://fi.wikipedia.org/wiki/Kes%C3%A4olympialaiset_1952", "Kesäolympialaiset 1952 – Wikipedia",
    "Vuoden 1952 kesäolympialaiset eli XV olympiadin kisat järjestettiin Helsingissä 19. heinäkuuta – 3. "
    "elokuuta 1952.")
EN_CARD = DraftCard(
    "Rick in Casablanca", "Humphrey Bogart played Rick Blaine in Casablanca.",
    "https://en.wikipedia.org/wiki/Casablanca_(film)", "Casablanca (film) - Wikipedia",
    "Bogart plays Rick Blaine, the owner of an upscale nightclub and gambling den in Casablanca.")
PPLX_USD, PPLX_OWN = 0.00812, 0.0081  # Carl's figure for a finding, and Perplexity's own
JEV_USD = 0.000021
SUPPORTED = ("supported", {"supported": 0.93, "not supported": 0.05, "doesn't answer the candidate": 0.02})


# --- Fakes -----------------------------------------------------------------------------------


def finding_record(request, **changes) -> CallRecord:
    call = CallRecord(STAGE_B, "perplexity", "google/gemini-3.8-flash", request.prompt.name, request.prompt.version,
                      request.values(), {"search_type": "web"}, input_tokens=6000, cached_tokens=0,
                      output_tokens=200, cost_usd=PPLX_USD, provider_cost_usd=PPLX_OWN, elapsed_s=5.1,
                      request={"input": "the rendered prompt"}, response={"output": []}, status=200)
    return dataclasses.replace(call, **changes)


def reply(outcome, card=None, snippet=None, url=None, restatement="Helsingin olympialaiset olivat vuonna 1956."):
    """A finding: its outcome, card, restatement, and a search result from
    the card's page whose snippet holds the excerpt, or `snippet`."""
    results = ()
    if card is not None:
        text = snippet if snippet is not None else f"Kisat. {card.excerpt} Lisää tekstiä."
        results = (SearchResult(url or card.source_url, card.source_title, text),
                   SearchResult("https://example.org/other", "Other", "Nothing to see here at all."))
    return outcome, card, restatement, results


class FakeFinder:
    """Fact-finder B giving the replies a test lines up, in order: `reply()`
    tuples, a typed error's kind, or an async function of the request
    returning one of those."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.requests = []

    async def find(self, request, *, stage):
        assert stage == STAGE_B
        self.requests.append(request)
        answer = self.replies.pop(0)
        if callable(answer):
            answer = await answer(request)
        if isinstance(answer, str):
            status = {"rate-limited": 429, "unavailable": 503}.get(answer)
            raise ModelError(answer, finding_record(request, input_tokens=1500, output_tokens=300, cost_usd=0.0023,
                                                    provider_cost_usd=None, estimated=True, error=answer,
                                                    error_text="the provider's full text", status=status,
                                                    response=None))
        outcome, card, restatement, results = answer
        return Finding(outcome, restatement, card, results, ("Helsingin olympialaiset",), 1,
                       "google/gemini-3.8-flash", False, finding_record(request))


def verdict_record(question, **changes) -> CallRecord:
    call = CallRecord("fact-checking", "openrouter", "typesafe/jev-1.13", question.prompt, question.version,
                      dict(question.fields), {}, input_tokens=500, cached_tokens=0, output_tokens=45,
                      cost_usd=JEV_USD, provider_cost_usd=JEV_USD, elapsed_s=0.3, request={"state": {}},
                      response={"answers": {}}, status=200)
    return dataclasses.replace(call, **changes)


class FakeTyped:
    """The fact-checking model: `(answer, probs)` replies or a typed error's kind."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.questions = []

    async def ask(self, question, *, stage):
        assert stage == "fact-checking"
        self.questions.append(question)
        answer = self.replies.pop(0)
        if isinstance(answer, str):
            raise ModelError(answer, verdict_record(question, error=answer, estimated=True, provider_cost_usd=None,
                                                    response=None, status=None))
        choice, probs = answer
        assert choice in question.choices
        return TypedAnswer(choice, probs, verdict_record(question))


class FakeLink:
    def __init__(self):
        self.sent = []

    async def send(self, message):
        self.sent.append(message)


# --- Fixtures and helpers ------------------------------------------------------------------------


@pytest.fixture
def prompts():
    return load_prompts(ROOT / "prompts")


@pytest.fixture
def sessions(config, prompts, store, stt):
    return Sessions(config, prompts, store, stt, "test")


@pytest.fixture
def session(sessions):
    session = Session(sessions, "20260927T180000Z-abcdef", record=True, timezone="Europe/Helsinki")
    session.recorder = Events()
    session.link = FakeLink()
    return session


def say(session, text, ago=2.0, speaker="1", stream=1, language="fi") -> Heard:
    """An utterance that ended `ago` seconds ago, added to the session's list."""
    session.utterance_count += 1
    heard = Heard(f"U{session.utterance_count}", stream, Utterance(speaker, words(speaker, text, language=language)),
                  time.time() - ago)
    session.heard.append(heard)
    return heard


def flag(session, heard, kind="claim") -> Candidate:
    """The decision call's candidate for `heard`."""
    language = card_language(session.heard, heard, session.config.card_language)
    candidate = Candidate(f"C{len(session.candidates) + 1}", kind, heard, 0.9, language)
    session.candidates.append(candidate)
    return candidate


async def check(sessions, session, candidate, finder, model=None) -> Checker:
    checker = Checker(sessions, finder, model or FakeTyped())
    await checker.start(session, candidate)
    return checker


def olympics(session) -> Candidate:
    say(session, "Helsingissä on ollut olympialaisetkin.", ago=6)
    return flag(session, say(session, "Joo, vuonna 1956. Isä kävi katsomassa.", speaker="2"))


# --- Silent outcomes ----------------------------------------------------------------------------------


@pytest.mark.parametrize("outcome, reason", [("claim is right", "silent:claim-right"),
                                             ("not found", "silent:not-found")])
async def test_no_draft_card_is_silent(sessions, session, outcome, reason):
    candidate = olympics(session)
    model = FakeTyped()
    await check(sessions, session, candidate, FakeFinder(reply(outcome)), model)
    assert candidate.state == "silent" and model.questions == [] and session.cards == {}
    assert candidate.restatement == "Helsingin olympialaiset olivat vuonna 1956."
    assert [e["event"] for e in session.recorder.events] == ["model call", "finding", "band", "check"]
    assert session.recorder.of("band")[0] == {"event": "band", "candidate": "C1", "band": "none", "reason": reason,
                                              "shown": None}
    assert session.recorder.of("check")[0]["state"] == "silent" and session.link.sent == []


# --- The bands -----------------------------------------------------------------------------------------


@pytest.mark.parametrize("finding, verdict, band, reason, asked", [
    (reply("claim is wrong", FI_CARD), SUPPORTED, "hedged", "hedged:single-verified", True),
    (reply("claim is wrong", FI_CARD), ("supported", {"supported": 0.6, "not supported": 0.4}), "hedged",
     "hedged:single-verified", True),
    (reply("claim is wrong", FI_CARD), ("supported", None), "hedged", "hedged:single-verified", True),
    (reply("claim is wrong", FI_CARD), ("supported", {"supported": 0.55, "not supported": 0.45}), "none",
     "silent:low-support", True),
    (reply("claim is wrong", FI_CARD), ("not supported", {"supported": 0.2, "not supported": 0.8}), "none",
     "silent:not-supported", True),
    (reply("claim is wrong", FI_CARD), ("not supported", {"supported": 0.7, "not supported": 0.3}), "none",
     "silent:not-supported", True),
    (reply("claim is wrong", FI_CARD), ("doesn't answer the candidate", None), "none", "silent:doesnt-answer", True),
    (reply("claim is wrong", FI_CARD, snippet="Helsingin kisat pidettiin kesällä 1952 monella areenalla."),
     None, "none", "silent:unverified", False),
    (reply("claim is wrong", FI_CARD, url="https://fi.wikipedia.org/wiki/Helsinki"), None, "none",
     "silent:unverified", False),
    (reply("claim is wrong", dataclasses.replace(FI_CARD, source_url="https://www.youtube.com/watch?v=abc")),
     None, "none", "silent:blocklisted", False),
])
async def test_each_draft_card_gets_its_band(sessions, session, finding, verdict, band, reason, asked):
    candidate = olympics(session)
    model = FakeTyped(*([verdict] if verdict else []))
    await check(sessions, session, candidate, FakeFinder(finding), model)
    assert len(model.questions) == asked
    [recorded] = session.recorder.of("band")
    assert (recorded["band"], recorded["reason"]) == (band, reason)
    assert recorded["shown"] == ("B" if band == "hedged" else None)
    assert candidate.state == ("ready" if band == "hedged" else "silent")
    assert len(session.link.sent) == (band == "hedged") and len(session.cards) == (band == "hedged")
    if not asked:  # the call is saved, and the recording says why
        assert session.recorder.of("verdict skipped") == [{"event": "verdict skipped", "candidate": "C1",
                                                           "finder": "B", "reason": reason}]
        assert [e["stage"] for e in session.recorder.of("model call")] == ["fact-finding B"]


async def test_a_blocklisted_source_is_recorded(sessions, session):
    card = dataclasses.replace(FI_CARD, source_url="https://old.reddit.com/r/Suomi/comments/x")
    await check(sessions, session, olympics(session), FakeFinder(reply("claim is wrong", card)))
    assert session.recorder.of("blocklisted") == [{"event": "blocklisted", "candidate": "C1", "finder": "B",
                                                   "url": card.source_url, "suffix": "reddit.com"}]
    assert session.recorder.of("excerpt")[0]["verified"] is True  # a verified excerpt doesn't help


# --- The card ---------------------------------------------------------------------------------------------


async def test_a_hedged_card_in_finnish(sessions, session):
    candidate = olympics(session)
    await check(sessions, session, candidate, FakeFinder(reply("claim is wrong", FI_CARD)), FakeTyped(SUPPORTED))
    [message] = session.link.sent
    assert message["type"] == "card"
    card = message["card"]
    age = card.pop("age_s")
    assert card == {
        "id": "C1", "kind": "claim", "band": "hedged", "language": "fi", "label": "Väite", "tag": "Varauksin",
        "title": "Helsingin olympialaiset 1952",
        "fact": "Todennäköisesti: Helsingin kesäolympialaiset pidettiin vuonna 1952, ei 1956.",
        "source": {"url": FI_CARD.source_url, "title": "Kesäolympialaiset 1952 – Wikipedia"},
        "utterance_time": card["utterance_time"],
    }
    assert 1.9 <= age <= 3.0  # the utterance ended 2 s ago
    assert card["utterance_time"] == iso_time(candidate.heard.time) and card["utterance_time"].endswith("Z")
    assert session.cards["C1"].state == "ready" and session.cards["C1"].candidate is candidate


async def test_a_hedged_answer_in_english(sessions, session):
    say(session, "I watched Casablanca again last night.", ago=5, language="en")
    candidate = flag(session, say(session, "Who played Rick in it?", speaker="2", language="en"), "open question")
    finder = FakeFinder(reply("question answered", EN_CARD, restatement="Who played Rick in Casablanca?"))
    await check(sessions, session, candidate, finder, FakeTyped(SUPPORTED))
    card = session.link.sent[0]["card"]
    assert (card["kind"], card["language"], card["label"], card["tag"]) == ("question", "en", "Question", "Hedged")
    assert card["fact"] == "Probably: Humphrey Bogart played Rick Blaine in Casablanca."
    assert card["title"] == "Rick in Casablanca" and card["source"]["title"] == "Casablanca (film) - Wikipedia"
    assert finder.requests[0].card_language == "English" and finder.requests[0].candidate_kind == "open question"


async def test_the_card_language_is_the_candidates_not_the_sources(sessions, session):
    """A Finnish table asking about an English film gets a Finnish card from an English source."""
    say(session, " ".join(["sana"] * 60), ago=30)
    candidate = flag(session, say(session, "Who played Rick in Casablanca?", language="en"), "open question")
    assert candidate.card_language.language == "fi"
    finder = FakeFinder(reply("question answered", dataclasses.replace(EN_CARD, fact="Rickiä näytteli Bogart.")))
    await check(sessions, session, candidate, finder, FakeTyped(SUPPORTED))
    card = session.link.sent[0]["card"]
    assert (card["label"], card["tag"]) == ("Kysymys", "Varauksin")
    assert card["fact"] == "Todennäköisesti: Rickiä näytteli Bogart."
    assert finder.requests[0].card_language == "Finnish"


# --- What each model gets ---------------------------------------------------------------------------------


async def test_the_finder_gets_the_candidate_its_window_the_place_and_the_card_language(sessions, session):
    sessions.locator = Locator(sessions.config.location, Nominatim())
    session.place = Place("Kallio", "Helsinki", "Uusimaa", "Suomi / Finland", "FI")
    say(session, "Tämä jää ikkunan ulkopuolelle.", ago=200)
    say(session, "Helsingissä on ollut olympialaisetkin.", ago=6)
    session.heard.append(Marker("paused", time.time() - 5))
    candidate = flag(session, say(session, "Joo, vuonna 1956.", speaker="2", stream=2))
    finder = FakeFinder(reply("claim is right"))
    await check(sessions, session, candidate, finder)
    [request] = finder.requests
    assert request.prompt is sessions.prompts["fact-finding"]
    assert request.candidate_kind == "claim" and request.candidate == "B2: Joo, vuonna 1956."
    assert request.conversation == ("A1: Helsingissä on ollut olympialaisetkin.", "(paused)")
    assert request.conversation == tuple(window(session, candidate.heard))
    assert request.place_and_time.startswith("Kallio, Helsinki, Suomi / Finland. ")
    assert request.place_and_time.endswith("(Europe/Helsinki)")
    assert request.card_language == "Finnish"
    assert request.perplexity_location == {"country": "FI", "region": "Uusimaa", "city": "Helsinki"}
    [call] = session.recorder.of("model call")
    assert call["user_location"] == {"country": "FI", "region": "Uusimaa", "city": "Helsinki"}
    assert call["fields"]["place_and_time"] == request.place_and_time


async def test_without_location_the_finder_gets_the_date_and_time(sessions, session):
    finder = FakeFinder(reply("claim is right"))
    await check(sessions, session, olympics(session), finder)
    assert finder.requests[0].place_and_time.endswith("(Europe/Helsinki)")
    assert finder.requests[0].perplexity_location is None


async def test_the_verdict_gets_the_candidate_and_its_window_never_the_restatement(sessions, session):
    sessions.locator = Locator(sessions.config.location, Nominatim())
    session.place = Place("Kallio", "Helsinki", "Uusimaa", "Suomi / Finland", "FI")
    candidate = olympics(session)
    model = FakeTyped(SUPPORTED)
    await check(sessions, session, candidate, FakeFinder(reply("claim is wrong", FI_CARD)), model)
    [question] = model.questions
    assert question.prompt == "fact-checking" and question.version == sessions.prompts["fact-checking"].version
    fields = dict(question.fields)
    date_time = fields.pop("date_time")
    assert date_time.endswith("(Europe/Helsinki)") and "Kallio" not in date_time  # the date and time only
    assert fields == {
        "candidate": "A2: Joo, vuonna 1956. Isä kävi katsomassa.",
        "conversation": "A1: Helsingissä on ollut olympialaisetkin.",
        "card_title": FI_CARD.title, "card_fact": FI_CARD.fact, "excerpt": FI_CARD.excerpt,
    }
    assert candidate.restatement not in json.dumps(question.fields, ensure_ascii=False)
    assert list(question.choices) == ["supported", "not supported", "doesn't answer the candidate"]


def test_the_verdict_says_so_when_nothing_was_said_before():
    fields = verdict_fields("A1: Einstein reputti matikan.", [], EN_CARD, "Sunday 27 September 2026, 21:04 (UTC)")
    assert fields["conversation"] == "(nothing said before)"


# --- The restatement -----------------------------------------------------------------------------------------


async def test_the_restatement_replaces_the_raw_utterance_in_later_decisions(sessions, session):
    candidate = olympics(session)
    decider = Decider(sessions, DecisionModel(("none", {"none": 1.0}), ("none", {"none": 1.0})))
    await decider.on_utterance(session, say(session, "Niinkö?", ago=1))
    assert decider.model.questions[0].fields["earlier_candidates"] == "C1: Joo, vuonna 1956. Isä kävi katsomassa."
    finder = FakeFinder(reply("claim is right", restatement="Helsingin kesäolympialaiset pidettiin vuonna 1956."))
    await check(sessions, session, candidate, finder)
    assert session.recorder.of("finding")[0]["restatement"] == "Helsingin kesäolympialaiset pidettiin vuonna 1956."
    await decider.on_utterance(session, say(session, "Aha, no ei sitten.", ago=0.5))
    assert decider.model.questions[1].fields["earlier_candidates"] == (
        "C1: Helsingin kesäolympialaiset pidettiin vuonna 1956.")


async def test_the_restatement_arrives_before_the_verdict(sessions, session):
    candidate = olympics(session)
    seen = []

    class Watching(FakeTyped):
        async def ask(self, question, *, stage):
            seen.append((candidate.state, candidate.restatement))
            return await super().ask(question, stage=stage)

    await check(sessions, session, candidate, FakeFinder(reply("claim is wrong", FI_CARD)), Watching(SUPPORTED))
    assert seen == [("checking", "Helsingin olympialaiset olivat vuonna 1956.")]


# --- Failures and the rate-limited retry ------------------------------------------------------------------------


@pytest.fixture
def quick_retry(monkeypatch):
    monkeypatch.setattr(checks, "RETRY_AFTER_S", 0.01)


async def test_a_rate_limited_finding_is_tried_once_more(sessions, session, quick_retry):
    candidate = olympics(session)
    finder = FakeFinder("rate-limited", reply("claim is wrong", FI_CARD))
    await check(sessions, session, candidate, finder, FakeTyped(SUPPORTED))
    assert len(finder.requests) == 2 and finder.requests[0] == finder.requests[1]
    assert candidate.state == "ready"
    calls = [c for c in session.recorder.of("model call") if c["stage"] == STAGE_B]
    assert [(c["attempt"], c["error"], c["status"]) for c in calls] == [(1, "rate-limited", 429), (2, None, 200)]
    month = await sessions.costs.month()
    assert month["by_stage"]["fact-finding B"] == pytest.approx(0.0023 + PPLX_OWN)
    assert month["estimated_usd"] == pytest.approx(0.0023)


async def test_a_second_429_fails_the_candidate(sessions, session, quick_retry):
    candidate = olympics(session)
    finder = FakeFinder("rate-limited", "rate-limited")
    await check(sessions, session, candidate, finder)
    assert len(finder.requests) == 2 and candidate.state == "failed" and candidate.restatement is None
    assert session.recorder.of("check")[0] | {"after_s": 0} == {
        "event": "check", "candidate": "C1", "state": "failed", "after_s": 0, "stage": "fact-finding B",
        "error": "rate-limited"}


async def test_an_old_candidate_isnt_tried_again(sessions, session, quick_retry):
    candidate = flag(session, say(session, "Joo, vuonna 1956.", ago=12))
    finder = FakeFinder("rate-limited", reply("claim is right"))
    await check(sessions, session, candidate, finder)
    assert len(finder.requests) == 1 and candidate.state == "failed"


@pytest.mark.parametrize("kind", ["timeout", "unavailable", "bad output"])
async def test_a_failed_finding_fails_the_candidate(sessions, session, kind, quick_retry, caplog):
    candidate = olympics(session)
    finder = FakeFinder(kind, reply("claim is right"))
    with caplog.at_level(logging.WARNING, logger="carl.checks"):
        await check(sessions, session, candidate, finder)
    assert len(finder.requests) == 1  # only a 429 is tried again
    assert candidate.state == "failed" and session.cards == {}
    assert [e["event"] for e in session.recorder.events] == ["model call", "check"]
    call = session.recorder.of("model call")[0]
    assert call["error"] == kind and call["error_text"] == "the provider's full text" and call["estimated"] is True
    assert (await sessions.costs.month())["estimated_usd"] == pytest.approx(0.0023)
    assert "C1 failed" in caplog.text and "1956" not in caplog.text


async def test_a_failed_verdict_fails_the_candidate(sessions, session):
    candidate = olympics(session)
    await check(sessions, session, candidate, FakeFinder(reply("claim is wrong", FI_CARD)), FakeTyped("timeout"))
    assert candidate.state == "failed" and session.cards == {}
    assert session.recorder.of("verdict")[0] == {"event": "verdict", "candidate": "C1", "finder": "B",
                                                 "answer": None, "probs": None, "error": "timeout"}
    assert session.recorder.of("band")[0]["reason"] == "silent:no-verdict"
    [end] = session.recorder.of("check")
    assert (end["state"], end["stage"], end["error"]) == ("failed", "fact-checking", "timeout")
    assert (await sessions.costs.month())["by_stage"]["fact-checking"] == pytest.approx(JEV_USD)


async def test_a_bug_in_one_check_is_logged_not_raised(sessions, session, caplog):
    async def broken(request):
        raise RuntimeError("a bug")

    candidate = olympics(session)
    with caplog.at_level(logging.ERROR, logger="carl.checks"):
        await check(sessions, session, candidate, FakeFinder(broken))
    assert candidate.state == "failed" and "the check of C1 went wrong" in caplog.text


# --- Costs ----------------------------------------------------------------------------------------------------


async def test_each_call_is_charged_to_the_month_and_the_session(sessions, session):
    await check(sessions, session, olympics(session), FakeFinder(reply("claim is wrong", FI_CARD)),
                FakeTyped(SUPPORTED))
    month = await sessions.costs.month()
    # Perplexity's own figure counts, not the price table's.
    assert month["by_stage"] == {"fact-finding B": pytest.approx(PPLX_OWN), "fact-checking": pytest.approx(JEV_USD)}
    assert month["by_provider"] == {"perplexity": pytest.approx(PPLX_OWN), "openrouter": pytest.approx(JEV_USD)}
    assert month["charges"] == 2 and month["estimated_usd"] == 0
    assert session.cost_usd == pytest.approx(PPLX_OWN + JEV_USD)
    finding, verdict = session.recorder.of("model call")
    assert (finding["cost_usd"], finding["provider_cost_usd"]) == (PPLX_USD, PPLX_OWN)  # both kept


# --- The recording -----------------------------------------------------------------------------------------------


async def test_the_recording_keeps_the_whole_check(sessions, session):
    candidate = olympics(session)
    await check(sessions, session, candidate, FakeFinder(reply("claim is wrong", FI_CARD)), FakeTyped(SUPPORTED))
    log = session.recorder.events
    assert [e["event"] for e in log] == ["model call", "finding", "excerpt", "model call", "verdict", "band",
                                         "check", "card sent"]
    finding_call, finding, excerpt, verdict_call, verdict, band, done, sent = log
    assert finding_call["candidate"] == "C1" and finding_call["utterance"] == "U2" and finding_call["attempt"] == 1
    assert finding_call["stage"] == "fact-finding B" and finding_call["prompt"] == "fact-finding"
    assert finding_call["fields"]["candidate"] == "A2: Joo, vuonna 1956. Isä kävi katsomassa."
    assert finding_call["fields"]["card_language"] == "Finnish"
    assert "request" not in finding_call and "request" not in verdict_call
    assert finding["finder"] == "B" and finding["outcome"] == "claim is wrong"
    assert finding["restatement"] == "Helsingin olympialaiset olivat vuonna 1956."
    assert finding["card"] == dataclasses.asdict(FI_CARD) and finding["source_in_results"] is True
    assert finding["results"][0]["snippet"].startswith("Kisat. Vuoden 1952") and finding["search_calls"] == 1
    assert finding["model"] == "google/gemini-3.8-flash" and finding["model_differs"] is False
    assert excerpt == {"event": "excerpt", "candidate": "C1", "finder": "B", "method": "snippet", "verified": True}
    assert verdict_call["stage"] == "fact-checking" and verdict_call["finder"] == "B"
    assert set(verdict_call["fields"]) == {"date_time", "conversation", "candidate", "card_title", "card_fact",
                                           "excerpt"}
    assert verdict == {"event": "verdict", "candidate": "C1", "finder": "B", "answer": "supported",
                       "probs": SUPPORTED[1]}
    assert band == {"event": "band", "candidate": "C1", "band": "hedged", "reason": "hedged:single-verified",
                    "shown": "B"}
    assert done["state"] == "ready" and done["band"] == "hedged" and 1.9 <= done["after_s"] <= 3
    assert sent["id"] == "C1" and sent["page"] is True and sent["fact"].startswith("Todennäköisesti: ")
    assert sent["age_s"] == session.link.sent[0]["card"]["age_s"]
    json.dumps(log)  # all of it fits the JSONL log


# --- Card state on the server --------------------------------------------------------------------------------------


def card(session, cid, ago, state="ready") -> Card:
    card = Card(cid, {"id": cid, "title": cid}, time.time() - ago, state=state)
    session.cards[cid] = card
    return card


async def test_the_pages_reports_move_a_card_on(sessions, session):
    candidate = olympics(session)
    await check(sessions, session, candidate, FakeFinder(reply("claim is wrong", FI_CARD)), FakeTyped(SUPPORTED))
    sent = session.cards["C1"]
    session.card_reported("shown", "C1", "2026-09-27T18:04:36.100Z")
    assert sent.state == candidate.state == "on screen" and sent.shown_at == "2026-09-27T18:04:36.100Z"
    session.card_reported("filed", "C1", "2026-09-27T18:04:50.000Z", late=False)
    assert sent.state == candidate.state == "card history"
    assert (sent.filed_at, sent.late) == ("2026-09-27T18:04:50.000Z", False)
    shown, filed = session.recorder.of("card shown") + session.recorder.of("card filed")
    assert shown["id"] == "C1" and shown["at"] == "2026-09-27T18:04:36.100Z" and shown["state"] == "on screen"
    assert shown["received"].endswith("Z") and 1.9 <= shown["age_s"] <= 3
    assert filed["late"] is False and filed["state"] == "card history"


def test_a_card_never_moves_back(sessions, session):
    filed = card(session, "C1", 30)
    session.card_reported("filed", "C1", "2026-09-27T18:05:00.000Z", late=True)  # late, never shown
    session.card_reported("shown", "C1", "2026-09-27T18:04:59.000Z")  # queued before it, arriving after
    assert filed.state == "card history" and filed.late is True and filed.shown_at == "2026-09-27T18:04:59.000Z"
    assert [e["state"] for e in session.recorder.events] == ["card history", "card history"]
    session.card_reported("filed", "C1", "2026-09-27T18:06:00.000Z", late=False)
    assert filed.filed_at == "2026-09-27T18:05:00.000Z" and filed.late is True  # the first report stands
    shown = card(session, "C2", 5, state="on screen")
    session.card_reported("shown", "C2", "2026-09-27T18:05:01.000Z")
    assert shown.state == "on screen"


def test_a_report_for_a_card_never_sent_changes_nothing(sessions, session, caplog):
    with caplog.at_level(logging.WARNING, logger="carl.session"):
        session.card_reported("shown", "C9", 12345)
    assert session.cards == {} and "never sent" in caplog.text
    assert session.recorder.events[0]["at"] is None and session.recorder.events[0]["state"] is None


def test_the_cards_message_rebuilds_the_screen(sessions, session):
    card(session, "C1", 90, "card history")
    card(session, "C2", 60, "card history")
    card(session, "C3", 30, "on screen").shown_received = time.time() - 20
    card(session, "C5", 10)
    card(session, "C4", 15)
    message = session.cards_message()
    assert message["type"] == "cards"
    assert message["current"]["id"] == "C3" and 29.9 <= message["current"]["age_s"] <= 31
    assert [c["id"] for c in message["waiting"]] == ["C4", "C5"]  # utterance order
    assert [c["id"] for c in message["history"]] == ["C2", "C1"]  # newest first
    assert all("age_s" in c for c in message["waiting"] + message["history"])


def test_of_two_cards_on_screen_the_one_shown_last_is_current(sessions, session):
    card(session, "C1", 30, "on screen").shown_received = time.time() - 10
    card(session, "C2", 20, "on screen").shown_received = time.time() - 25
    message = session.cards_message()
    assert message["current"]["id"] == "C1" and [c["id"] for c in message["history"]] == ["C2"]
    assert message["waiting"] == []


def test_nothing_on_screen(sessions, session):
    card(session, "C1", 30)
    assert session.cards_message()["current"] is None


# --- The decision call starts the check -------------------------------------------------------------------------


async def test_the_decision_call_starts_a_check_for_each_new_candidate(sessions, session):
    sessions.checker = Checker(sessions, FakeFinder(reply("claim is right")), FakeTyped())
    decider = Decider(sessions, DecisionModel(("claim", {"claim": 1.0}), ("none", {"none": 1.0})))
    await decider.on_utterance(session, say(session, "Joo, vuonna 1956."))
    [candidate] = session.candidates
    assert candidate.state == "finding" and len(session.checks) == 1
    await asyncio.gather(*session.checks)
    assert candidate.state == "silent"
    await decider.on_utterance(session, say(session, "Otatko kahvia?"))
    assert session.checks == set()


async def test_a_candidate_flagged_after_end_is_dropped_before_any_search(sessions, session):
    session.state = "ended"
    candidate = olympics(session)
    finder = FakeFinder()
    await check(sessions, session, candidate, finder)
    assert finder.requests == [] and candidate.state == "dropped"
    assert session.recorder.of("check")[0]["reason"] == "session ended"


async def test_a_card_ready_after_end_is_dropped(sessions, session):
    candidate = olympics(session)

    async def ends(request):
        session.state = "ended"
        return reply("claim is wrong", FI_CARD)

    await check(sessions, session, candidate, FakeFinder(ends), FakeTyped(SUPPORTED))
    assert candidate.state == "dropped" and session.cards == {} and session.link.sent == []
    assert session.recorder.of("band")[0]["band"] == "hedged"


# --- Installing it ------------------------------------------------------------------------------------------------


def test_without_the_keys_there_are_no_checks(sessions, caplog):
    with caplog.at_level(logging.WARNING, logger="carl.checks"):
        checks.install(sessions, {"PERPLEXITY_API_KEY": "pplx-test"})
    assert sessions.checker is None
    assert "no checks: OPENROUTER_API_KEY not set" in caplog.text


def test_with_the_keys_the_models_are_made_on_their_first_call(sessions):
    checks.install(sessions, {"PERPLEXITY_API_KEY": "pplx-test", "OPENROUTER_API_KEY": "sk-or-test"})
    checker = sessions.checker
    assert isinstance(checker, Checker) and isinstance(checker.finder, LazyFinder)
    assert isinstance(checker.model, LazyModel)
    assert checker.finder.finder is None and checker.model.model is None


def test_a_mistake_in_a_checking_stage_stops_startup(sessions):
    stage = dataclasses.replace(sessions.config.stages.fact_finder_b, params={"temperatur": 0})
    sessions.config = dataclasses.replace(sessions.config,
                                          stages=dataclasses.replace(sessions.config.stages, fact_finder_b=stage))
    with pytest.raises(ValueError):
        checks.install(sessions, {"PERPLEXITY_API_KEY": "pplx-test", "OPENROUTER_API_KEY": "sk-or-test"})


# --- Through the WebSocket -----------------------------------------------------------------------------------------


class ClaimModel(DecisionModel):
    """The decision model: every utterance with a year in it is a claim."""

    async def ask(self, question, *, stage):
        self.replies = [("claim", {"claim": 0.97, "none": 0.03}) if "1956" in question.fields["utterance"]
                        else ("none", {"none": 1.0})]
        return await super().ask(question, stage=stage)


def plug(unlocked, prompts, finder, model=None) -> Sessions:
    sessions = unlocked.server.app[SESSIONS]
    sessions.prompts = prompts
    sessions.decider = Decider(sessions, ClaimModel())
    sessions.checker = Checker(sessions, finder, model or FakeTyped(SUPPORTED))
    return sessions


async def until(condition, timeout=2.0):
    deadline = time.monotonic() + timeout
    while not condition():
        assert time.monotonic() < deadline, "timed out"
        await asyncio.sleep(0.01)


async def test_a_spoken_claim_ends_as_a_card_on_the_page(unlocked, stt, store, prompts):
    sessions = plug(unlocked, prompts, FakeFinder(reply("claim is wrong", FI_CARD)))
    ws = await connect(unlocked)
    session_id = (await start(ws))["session"]
    stt.streams[0].say("1", "Helsingissä on ollut olympialaisetkin.")
    stt.streams[0].say("2", "Joo, vuonna 1956.", start_ms=3000)
    card = (await receive(ws, "card"))["card"]
    assert card["id"] == "C1" and card["kind"] == "claim" and card["label"] == "Väite"
    assert card["fact"] == "Todennäköisesti: Helsingin kesäolympialaiset pidettiin vuonna 1952, ei 1956."
    assert card["source"]["url"] == FI_CARD.source_url and card["age_s"] >= 0
    session = sessions.get(session_id)
    await ws.send_json({"type": "card_shown", "id": "C1", "at": "2026-09-27T18:04:36.100Z"})
    await until(lambda: session.cards["C1"].state == "on screen")
    await ws.send_json({"type": "card_filed", "id": "C1", "at": "2026-09-27T18:04:50.000Z", "late": False})
    await until(lambda: session.cards["C1"].state == "card history")
    assert session.candidates[0].state == "card history"
    await ws.send_json({"type": "end"})
    ended = await receive(ws, "ended")
    assert ended["summary"]["cards"] == 1
    log = await events(store, session_id)
    names = [e["event"] for e in log]
    for name in ("candidate", "finding", "excerpt", "verdict", "band", "check", "card sent", "card shown",
                 "card filed"):
        assert name in names
    assert names.index("card filed") < names.index("session end")
    [finding_call] = [e for e in log if e["event"] == "model call" and e["stage"] == "fact-finding B"]
    assert finding_call["fields"]["conversation"] == "A1: Helsingissä on ollut olympialaisetkin."
    assert [e for e in log if e["event"] == "session end"][0]["cards"] == 1


async def test_a_card_ready_while_the_page_is_away_comes_with_the_rejoin(unlocked, stt, prompts):
    found = asyncio.Event()

    async def later(request):
        await found.wait()
        return reply("claim is wrong", FI_CARD)

    sessions = plug(unlocked, prompts, FakeFinder(later))
    ws = await connect(unlocked)
    session_id = (await start(ws))["session"]
    session = sessions.get(session_id)
    stt.streams[0].say("1", "Joo, vuonna 1956.")
    await until(lambda: session.candidates and session.candidates[0].state == "finding")
    await ws.close()
    await settle()
    found.set()
    await until(lambda: "C1" in session.cards)
    assert session.recorder is not None and session.link is None
    ws = await connect(unlocked)
    await ws.send_json({"type": "rejoin", "session": session_id})
    await receive(ws, "session")
    cards = await receive(ws, "cards")
    assert cards["current"] is None and cards["history"] == []
    [waiting] = cards["waiting"]
    assert waiting["id"] == "C1" and waiting["fact"].startswith("Todennäköisesti: ") and waiting["age_s"] >= 0
    await ws.send_json({"type": "card_shown", "id": "C1", "at": "2026-09-27T18:04:36.100Z"})
    await until(lambda: session.cards["C1"].state == "on screen")
    await ws.close()
    await settle()
    ws = await connect(unlocked)
    await ws.send_json({"type": "rejoin", "session": session_id})
    await receive(ws, "session")
    cards = await receive(ws, "cards")
    assert cards["current"]["id"] == "C1" and cards["waiting"] == []
    await ws.send_json({"type": "end"})
    assert (await receive(ws, "ended"))["summary"]["cards"] == 1


async def test_end_waits_for_a_check_still_running(unlocked, stt, store, prompts):
    async def slow(request):
        await asyncio.sleep(0.3)
        return reply("claim is wrong", FI_CARD)

    sessions = plug(unlocked, prompts, FakeFinder(slow))
    ws = await connect(unlocked)
    session_id = (await start(ws))["session"]
    session = sessions.get(session_id)
    stt.streams[0].say("1", "Joo, vuonna 1956.")
    await until(lambda: session.candidates and session.candidates[0].state == "finding")
    await ws.send_json({"type": "end"})
    ended = await receive(ws, "ended")
    assert ended["summary"]["cards"] == 0  # its card was ready only after End
    log = await events(store, session_id)
    names = [e["event"] for e in log]
    assert names.index("finding") < names.index("check") < names.index("session end")
    assert [e for e in log if e["event"] == "check"][0]["state"] == "dropped"
