import asyncio
import dataclasses
import json
import logging
import re
from datetime import UTC, datetime

import pytest

from carl import decision
from carl.decision import Candidate, Decider, LazyModel, date_time, is_backchannel, outcome, stream_letters
from carl.models import CallRecord, ModelError, TypedAnswer
from carl.prompts import load_prompts
from carl.server import SESSIONS, create_app
from carl.session import Heard, Marker, Session, Sessions
from carl.stt.fake import words
from carl.utterances import Utterance

from .conftest import ROOT

T0 = 1_790_000_000.0
DISCLOSURE = {"text": "Tämä on testi. …", "confirmed_at": "2026-09-27T18:02:11.123Z"}
USD = 0.0000585  # 520 input and 13 output tokens at Luna's prices


def record(question, **changes) -> CallRecord:
    call = CallRecord("decision", "openai", "gpt-6-luna", question.prompt, question.version, dict(question.fields),
                      {"reasoning_effort": "none"}, input_tokens=520, cached_tokens=0, output_tokens=13,
                      cost_usd=USD, elapsed_s=0.9, request={"input": "the rendered prompt"},
                      response={"output": [{"type": "message"}]}, status=200)
    return dataclasses.replace(call, **changes)


class FakeModel:
    """A decision model that gives the answers a test lines up, in order.

    Each reply is `(answer, probs)`, a typed error's kind, or an async
    function of the question returning one of those. With none left it
    answers `none`.
    """

    def __init__(self, *replies):
        self.replies = list(replies)
        self.questions = []

    async def ask(self, question, *, stage):
        assert stage == "decision"
        self.questions.append(question)
        reply = self.replies.pop(0) if self.replies else ("none", {"none": 1.0})
        if callable(reply):
            reply = await reply(question)
        if isinstance(reply, str):
            raise ModelError(reply, record(question, input_tokens=600, output_tokens=15, cost_usd=0.0000675,
                                           estimated=True, error=reply, error_text="no answer within 20 s",
                                           response=None, status=None))
        answer, probs = reply
        assert answer in question.choices
        return TypedAnswer(answer, probs, record(question))


class Events:
    """Stands in for a session's recorder, keeping its events in a list."""

    active = True

    def __init__(self):
        self.events = []

    def log(self, event, **fields):
        self.events.append({"event": event, **fields})

    def of(self, kind):
        return [e for e in self.events if e["event"] == kind]


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
    return session


def say(session, text, at, speaker="1", stream=1, language="fi") -> Heard:
    """An utterance heard `at` seconds into the session, added to its list."""
    session.utterance_count += 1
    heard = Heard(f"U{session.utterance_count}", stream, Utterance(speaker, words(speaker, text, language=language)),
                  T0 + at)
    session.heard.append(heard)
    return heard


async def decide(sessions, session, heard, *replies) -> FakeModel:
    model = FakeModel(*replies)
    await Decider(sessions, model).on_utterance(session, heard)
    return model


# --- The backchannel skip ---------------------------------------------------------------


@pytest.mark.parametrize("text", ["Joo.", "joo joo niin", "Mm, aha.", "Öö… jaa.", "Okei!", "Yeah, right.", "Uh-huh.",
                                  "Wow", "Oh okay."])
async def test_backchannel_is_skipped(sessions, session, text):
    heard = say(session, text, at=10)
    model = await decide(sessions, session, heard)
    assert model.questions == []
    assert session.recorder.events == [{"event": "decision skipped", "utterance": "U1"}]


@pytest.mark.parametrize("text", ["Kuka se oli?", "'53 vai '54?", "Joo, kuka se oli?", "Yeah, who was it?", "Mitä?"])
async def test_short_questions_are_judged(sessions, session, text):
    model = await decide(sessions, session, say(session, text, at=10))
    assert len(model.questions) == 1
    assert session.recorder.of("decision skipped") == []


def test_the_backchannel_list_is_matched_by_whole_words():
    listed = frozenset({"joo", "uh-huh", "öö"})
    assert is_backchannel(["JOO,", "Uh-huh…", "“öö”"], listed)
    assert not is_backchannel(["joo", "kiitos"], listed)
    assert not is_backchannel(["jooo"], listed)
    assert not is_backchannel(["uh"], listed)


async def test_a_skipped_utterance_still_appears_in_later_context(sessions, session):
    await decide(sessions, session, say(session, "Joo.", at=10))
    model = await decide(sessions, session, say(session, "Kuka se oli?", at=12, speaker="2"))
    assert model.questions[0].fields["conversation"] == "A1: Joo."
    assert model.questions[0].fields["utterance"] == "A2: Kuka se oli?"


# --- The context ------------------------------------------------------------------------


async def test_the_context_holds_up_to_ten_earlier_utterances(sessions, session):
    for i in range(12):
        say(session, f"Lause numero {i}.", at=i)
    model = await decide(sessions, session, say(session, "Kuka se oli?", at=20, speaker="2"))
    fields = model.questions[0].fields
    assert fields["conversation"].splitlines() == [f"A1: Lause numero {i}." for i in range(2, 12)]
    assert fields["utterance"] == "A2: Kuka se oli?"
    assert list(fields) == ["place_and_time", "earlier_candidates", "conversation", "utterance"]


async def test_the_context_reaches_back_no_more_than_two_minutes(sessions, session):
    say(session, "Liian vanha.", at=0)
    say(session, "Juuri ja juuri.", at=1)
    model = await decide(sessions, session, say(session, "Kuka se oli?", at=121))
    assert model.questions[0].fields["conversation"] == "A1: Juuri ja juuri."


async def test_nothing_said_before_is_said_so(sessions, session):
    model = await decide(sessions, session, say(session, "Kuka se oli?", at=0))
    assert model.questions[0].fields["conversation"] == "(nothing said before)"
    assert model.questions[0].fields["earlier_candidates"] == "(none yet)"


async def test_the_context_holds_only_earlier_speech(sessions, session):
    say(session, "Ennen.", at=0)
    judged = say(session, "Kuka se oli?", at=1)
    say(session, "Jälkeen.", at=2)  # heard before the judged utterance's task ran
    model = await decide(sessions, session, judged)
    assert model.questions[0].fields["conversation"] == "A1: Ennen."


async def test_markers_and_labels_unique_across_streams(sessions, session):
    say(session, "Tuo suolaa.", at=0)
    session.heard.append(Marker("paused", T0 + 5))
    say(session, "Einstein reputti matikan.", at=30, stream=2)
    session.heard.append(Marker("gap", T0 + 40))
    model = await decide(sessions, session, say(session, "Kuka sanoi?", at=50, speaker="2", stream=3))
    fields = model.questions[0].fields
    assert fields["conversation"] == "A1: Tuo suolaa.\n(paused)\nB1: Einstein reputti matikan.\n(gap)"
    assert fields["utterance"] == "C2: Kuka sanoi?"


async def test_a_marker_with_nothing_before_it_in_the_window_is_left_out(sessions, session):
    say(session, "Kauan sitten.", at=0)
    session.heard.append(Marker("paused", T0 + 10))
    model = await decide(sessions, session, say(session, "Kuka se oli?", at=500, stream=2))
    assert model.questions[0].fields["conversation"] == "(nothing said before)"


def test_each_stream_gets_its_own_letters():
    assert [stream_letters(n) for n in (1, 2, 26, 27, 28, 52, 53)] == ["A", "B", "Z", "AA", "AB", "AZ", "BA"]


async def test_the_earlier_candidates_are_listed_by_id(sessions, session):
    first = say(session, "Einstein reputti matikan koulussa.", at=0)
    await decide(sessions, session, first, ("claim", {"claim": 1.0}))
    second = say(session, "Helsingin olympialaiset oli 1956.", at=5)
    await decide(sessions, session, second, ("claim", {"claim": 1.0}))
    session.candidates[1].restatement = "When were the Helsinki Olympics held?"
    model = await decide(sessions, session, say(session, "Se reputti kyllä.", at=10))
    question = model.questions[0]
    assert question.fields["earlier_candidates"] == (
        "C1: Einstein reputti matikan koulussa.\nC2: When were the Helsinki Olympics held?"
    )
    assert list(question.choices) == ["claim", "open question", "same as C1", "same as C2", "none"]


async def test_without_location_the_call_gets_the_local_date_time_and_timezone(sessions, session):
    model = await decide(sessions, session, say(session, "Kuka se oli?", at=0))
    place_and_time = model.questions[0].fields["place_and_time"]
    assert re.fullmatch(r"\w+day \d{1,2} \w+ \d{4}, \d\d:\d\d \(Europe/Helsinki\)", place_and_time)


async def test_with_location_the_call_gets_the_place_too(sessions, session):
    class Locator:
        def place_and_time(self, session, with_place):
            assert with_place
            return "Kallio, Helsinki, Finland. Sunday 27 September 2026, 21:04 (Europe/Helsinki)"

    sessions.locator = Locator()
    model = await decide(sessions, session, say(session, "Kuka se oli?", at=0))
    assert model.questions[0].fields["place_and_time"].startswith("Kallio, Helsinki, Finland. Sunday")


def test_the_date_and_time_are_local():
    when = datetime(2026, 9, 27, 18, 4, tzinfo=UTC)
    assert date_time("Europe/Helsinki", when) == "Sunday 27 September 2026, 21:04 (Europe/Helsinki)"
    assert date_time("America/New_York", when) == "Sunday 27 September 2026, 14:04 (America/New_York)"
    assert date_time("Not/AZone", when) == "Sunday 27 September 2026, 18:04 (UTC)"
    assert date_time("", when) == "Sunday 27 September 2026, 18:04 (UTC)"


# --- From probabilities to an outcome ----------------------------------------------------


def test_with_no_probabilities_the_chosen_answer_is_taken():
    assert outcome("claim", None, 0.5, 0.5) == ("claim", None)
    assert outcome("open question", None, 0.5, 0.5) == ("open question", None)
    assert outcome("same as C2", None, 0.5, 0.5) == ("same as C2", None)
    assert outcome("none", None, 0.5, 0.5) == ("none", None)


def test_the_same_as_choices_together_make_a_repeat_of_the_most_likely():
    probs = {"same as C1": 0.2, "same as C2": 0.3, "claim": 0.45, "other": 0.05}
    assert outcome("claim", probs, 0.5, 0.5) == ("same as C2", 0.3)
    assert outcome("claim", {"same as C1": 0.2, "same as C2": 0.25, "claim": 0.55}, 0.5, 0.5) == ("claim", 0.55)


def test_a_pooled_same_as_is_a_repeat_of_an_unknown_candidate():
    """Precision over recall: a likely repeat that can't be named gets nothing."""
    assert outcome("claim", {"same as *": 0.55, "claim": 0.45}, 0.5, 0.5) == ("same as *", 0.55)
    assert outcome("none", {"same as *": 0.6, "none": 0.4}, 0.5, 0.5) == ("same as *", 0.6)
    # With an id of its own in the running, the pooled rest still counts toward the total.
    probs = {"same as C1": 0.35, "same as *": 0.2, "claim": 0.45}
    assert outcome("same as C1", probs, 0.5, 0.5) == ("same as C1", 0.35)


def test_claim_and_open_question_together_make_a_candidate_of_the_more_likely_kind():
    assert outcome("none", {"claim": 0.3, "open question": 0.25, "none": 0.45}, 0.5, 0.5) == ("claim", 0.3)
    assert outcome("none", {"claim": 0.2, "open question": 0.3, "none": 0.5}, 0.5, 0.5) == ("open question", 0.3)
    assert outcome("claim", {"claim": 0.25, "open question": 0.25, "none": 0.5}, 0.5, 0.5) == ("claim", 0.25)
    assert outcome("claim", {"claim": 0.45, "open question": 0.04, "none": 0.51}, 0.5, 0.5) == ("none", 0.51)


def test_the_thresholds_come_from_the_config(config):
    probs = {"same as C1": 0.4, "claim": 0.35, "none": 0.25}
    assert outcome("same as C1", probs, 0.5, 0.5) == ("none", 0.25)
    assert outcome("same as C1", probs, 0.4, 0.5) == ("same as C1", 0.4)
    assert outcome("same as C1", probs, 0.5, 0.3) == ("claim", 0.35)
    assert config.decision.repeat_threshold == 0.5 and config.decision.candidate_threshold == 0.5


# --- Candidates, repeats and the recording -------------------------------------------------


async def test_a_claim_becomes_a_candidate(sessions, session):
    heard = say(session, "Einstein reputti matikan koulussa.", at=0)
    model = await decide(sessions, session, heard, ("claim", {"claim": 0.97, "none": 0.03}))
    [candidate] = session.candidates
    assert candidate == Candidate("C1", "claim", heard, 0.97, candidate.card_language)
    assert candidate.restatement is None and candidate.state == "recorded"
    assert candidate.card_language.language == "fi" and candidate.card_language.rule == "too few words"
    events = session.recorder.events
    assert [e["event"] for e in events] == ["model call", "candidate", "decision"]
    call = events[0]
    assert call["utterance"] == "U1" and call["stage"] == "decision" and call["prompt"] == "decision"
    assert call["version"] == sessions.prompts["decision"].version
    assert call["fields"] == dict(model.questions[0].fields)
    assert call["choices"] == ["claim", "open question", "none"]
    assert call["model"] == "gpt-6-luna" and call["params"] == {"reasoning_effort": "none"}
    assert call["input_tokens"] == 520 and call["output_tokens"] == 13 and call["elapsed_s"] == 0.9
    assert call["cost_usd"] == USD and call["estimated"] is False and call["error"] is None
    assert call["response"] == {"output": [{"type": "message"}]}
    assert "request" not in call  # the name, version and fields rebuild it
    assert events[1] == {"event": "candidate", "id": "C1", "kind": "claim", "utterance": "U1", "probability": 0.97,
                         "card_language": {"language": "fi", "rule": "too few words",
                                           "window_words": {"fi": 4}, "own_words": {"fi": 4}}}
    assert events[2] == {"event": "decision", "utterance": "U1", "outcome": "candidate", "candidate": "C1",
                         "answer": "claim", "probs": {"claim": 0.97, "none": 0.03}}
    json.dumps(events)  # all of it fits the JSONL log


async def test_an_open_question_becomes_a_candidate_with_the_next_id(sessions, session):
    await decide(sessions, session, say(session, "Einstein reputti matikan.", at=0), ("claim", None))
    await decide(sessions, session, say(session, "Kuka näytteli Rickiä?", at=5), ("open question", None))
    assert [(c.id, c.kind, c.heard.id, c.probability) for c in session.candidates] == [
        ("C1", "claim", "U1", None), ("C2", "open question", "U2", None)]


async def test_a_candidates_card_language_counts_only_what_came_before(sessions, session):
    say(session, " ".join(["sana"] * 60), at=0)
    heard = say(session, "Einstein failed maths at school.", at=10, language="en")
    say(session, " ".join(["word"] * 100), at=20, language="en")  # heard later
    await decide(sessions, session, heard, ("claim", {"claim": 1.0}))
    language = session.candidates[0].card_language
    assert language.language == "fi" and language.window == {"fi": 60, "en": 5} and language.own == {"en": 5}
    assert session.recorder.of("candidate")[0]["card_language"]["rule"] == "most words"


async def test_a_repeat_links_to_the_candidate_it_matched(sessions, session):
    await decide(sessions, session, say(session, "Einstein failed maths.", at=0), ("claim", {"claim": 1.0}))
    await decide(sessions, session, say(session, "Helsinki 1956.", at=5), ("claim", {"claim": 1.0}))
    session.recorder.events.clear()
    probs = {"same as C1": 0.8, "same as C2": 0.05, "claim": 0.15}
    await decide(sessions, session, say(session, "He did fail maths, though.", at=10), ("same as C1", probs))
    assert len(session.candidates) == 2
    assert session.recorder.of("repeat") == [{"event": "repeat", "utterance": "U3", "candidate": "C1",
                                              "probability": 0.8}]
    assert session.recorder.of("decision") == [{"event": "decision", "utterance": "U3", "outcome": "repeat",
                                                "candidate": "C1", "answer": "same as C1", "probs": probs}]


async def test_none_is_recorded_as_the_decision(sessions, session):
    await decide(sessions, session, say(session, "Otatko kahvia?", at=0), ("none", {"none": 1.0}))
    assert session.candidates == []
    assert [e["event"] for e in session.recorder.events] == ["model call", "decision"]
    assert session.recorder.of("decision")[0]["outcome"] == "none"


# --- Cost, failures and running side by side ------------------------------------------------


async def test_each_call_is_charged_to_the_month_and_the_session(sessions, session):
    await decide(sessions, session, say(session, "Einstein reputti matikan.", at=0), ("claim", None))
    month = await sessions.costs.month()
    assert month["by_stage"] == {"decision": pytest.approx(USD)}
    assert month["by_provider"] == {"openai": pytest.approx(USD)}
    assert month["estimated_usd"] == 0 and month["charges"] == 1
    assert session.cost_usd == pytest.approx(USD)


async def test_a_failed_call_drops_its_utterance_and_is_charged_an_estimate(sessions, session, caplog):
    heard = say(session, "Einstein reputti matikan.", at=0)
    with caplog.at_level(logging.WARNING, logger="carl.decision"):
        model = await decide(sessions, session, heard, "timeout", ("claim", None))
    assert len(model.questions) == 1  # never retried
    assert session.candidates == []
    call, dropped = session.recorder.events
    assert call["event"] == "model call" and call["utterance"] == "U1"
    assert call["error"] == "timeout" and call["error_text"] == "no answer within 20 s" and call["estimated"] is True
    assert dropped == {"event": "decision", "utterance": "U1", "outcome": "dropped", "error": "timeout"}
    month = await sessions.costs.month()
    assert month["usd"] == pytest.approx(0.0000675) and month["estimated_usd"] == pytest.approx(0.0000675)
    assert "U1 is dropped" in caplog.text and "Einstein" not in caplog.text


async def test_calls_run_side_by_side_and_a_newer_one_never_cancels_an_older_one(sessions, session):
    release = asyncio.Event()

    async def slow(question):
        await release.wait()
        return "claim", {"claim": 1.0}

    model = FakeModel(slow, ("open question", {"open question": 1.0}))
    sessions.decider = Decider(sessions, model)
    sessions.on_utterance(session, say(session, "Einstein reputti matikan.", at=0))
    sessions.on_utterance(session, say(session, "Oikeesti?", at=1, speaker="2"))
    for _ in range(20):
        await asyncio.sleep(0)
    assert len(model.questions) == 2 and model.questions[1].fields["conversation"] == "A1: Einstein reputti matikan."
    assert [c.heard.id for c in session.candidates] == ["U2"]
    release.set()
    await asyncio.gather(*session.tasks)
    assert [(c.id, c.heard.id) for c in session.candidates] == [("C1", "U2"), ("C2", "U1")]


async def test_a_bug_in_one_decision_is_logged_not_raised(sessions, session, caplog):
    async def broken(question):
        raise RuntimeError("a bug")

    with caplog.at_level(logging.ERROR, logger="carl.decision"):
        await decide(sessions, session, say(session, "Kuka se oli?", at=0), broken)
    assert "the decision on U1 went wrong" in caplog.text


# --- Installing it ------------------------------------------------------------------------------


def test_without_a_key_there_are_no_decision_calls(sessions, caplog):
    with caplog.at_level(logging.WARNING, logger="carl.decision"):
        decision.install(sessions, {})
    assert sessions.decider is None
    assert "no decision calls: OPENAI_API_KEY isn't set" in caplog.text


def test_with_a_key_the_configured_model_is_made_on_its_first_call(sessions):
    decision.install(sessions, {"OPENAI_API_KEY": "sk-test"})
    assert isinstance(sessions.decider, Decider) and isinstance(sessions.decider.model, LazyModel)
    assert sessions.decider.model.model is None


# --- Through the WebSocket ------------------------------------------------------------------------


@pytest.fixture
def model():
    return FakeModel(("claim", {"claim": 1.0}))


@pytest.fixture
async def client(aiohttp_client, app_config, passes, store, stt, prompts, model):
    sessions = Sessions(app_config, prompts, store, stt, "test")
    sessions.decider = Decider(sessions, model)
    return await aiohttp_client(create_app(app_config, prompts, passes, sessions))


async def receive(ws, kind):
    while True:
        message = await ws.receive_json(timeout=2)
        if message["type"] == kind:
            return message


async def test_a_spoken_claim_becomes_a_candidate_in_the_recording(unlocked, stt, store, model):
    ws = await unlocked.ws_connect("/api/ws")
    await receive(ws, "hello")
    await ws.send_json({"type": "start", "record": True, "disclosure": DISCLOSURE, "timezone": "Europe/Helsinki",
                        "mic": {"sampleRate": 16000}})
    session_id = (await receive(ws, "session"))["session"]
    session = unlocked.server.app[SESSIONS].get(session_id)
    stt.streams[0].say("1", "Joo.")
    stt.streams[0].say("2", "Einstein reputtasi matematiikassa.", start_ms=1000)
    for _ in range(100):
        if session.candidates:
            break
        await asyncio.sleep(0.01)
    await ws.send_json({"type": "end"})
    await receive(ws, "ended")
    log = []
    for key in await store.list(f"recordings/{session_id}/events/"):
        log += [json.loads(line) for line in (await store.get(key)).decode().splitlines()]
    assert [e["utterance"] for e in log if e["event"] == "decision skipped"] == ["U1"]
    [call] = [e for e in log if e["event"] == "model call"]
    assert call["utterance"] == "U2" and call["fields"]["utterance"] == "A2: Einstein reputtasi matematiikassa."
    assert call["fields"]["conversation"] == "A1: Joo."
    assert call["fields"]["place_and_time"].endswith("(Europe/Helsinki)")
    [candidate] = [e for e in log if e["event"] == "candidate"]
    assert candidate["id"] == "C1" and candidate["kind"] == "claim" and candidate["utterance"] == "U2"
    assert candidate["card_language"]["language"] == "fi"
    assert [e["outcome"] for e in log if e["event"] == "decision"] == ["candidate"]
    assert len(model.questions) == 1


def test_a_mistake_in_the_decision_stage_stops_startup(sessions):
    stage = dataclasses.replace(sessions.config.stages.decision, params={"reasoning_effort": "none", "temperatur": 0})
    stages = dataclasses.replace(sessions.config.stages, decision=stage)
    sessions.config = dataclasses.replace(sessions.config, stages=stages)
    with pytest.raises(ValueError):
        decision.install(sessions, {"OPENAI_API_KEY": "sk-test"})
