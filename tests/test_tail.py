import json

import pytest

from carl import cli, owner, tail
from carl.owner import OwnerError
from carl.storage import MemoryStore

SESSION = "20260927T175631Z-308317"
OLDER = "20260920T170000Z-0f0f0f"
EVENTS = f"recordings/{SESSION}/events/"


def jsonl(*events: dict) -> bytes:
    return b"".join(json.dumps(e, ensure_ascii=False).encode() + b"\n" for e in events)


def call(time: str, utterance: str, text: str, stage: str = "decision", **record) -> dict:
    fields = {"place_and_time": "Espoo. Sunday 27 September 2026, 20:57 (Europe/Helsinki)",
              "conversation": "A2: Mainitsit A-studion.", "utterance": text}
    return {"time": time, "event": "model call", "utterance": utterance, "stage": stage, "provider": "openai",
            "model": "gpt-6-luna", "prompt": stage, "version": "d64708e0", "fields": fields,
            "elapsed_s": 1.206, "input_tokens": 571, "output_tokens": 13, "cost_usd": 6.36e-05,
            "provider_cost_usd": None, "estimated": False, "response": {"output": "…"}, "status": 200,
            "error": None, "error_text": "", "error_code": None} | record


def outcome(time: str, utterance: str, stage: str = "decision", **fields) -> dict:
    return {"time": time, "event": stage, "utterance": utterance} | fields


def lines(*texts: str) -> list[str]:
    return [line for text in texts for line in text.split("\n")]


@pytest.fixture
def store() -> MemoryStore:
    store = MemoryStore()
    store.objects = {
        EVENTS + "000001.jsonl": jsonl(
            {"time": "2026-09-27T17:56:31.934Z", "event": "session start", "record": True},
            {"time": "2026-09-27T17:57:31.000Z", "event": "stt", "raw": {"tokens": []}},
            call("2026-09-27T17:57:32.602Z", "U3", "A1: Yleisradio saa 600 miljoonan euron vuotuisen rahoituksen."),
        ),
        # The outcome in the next part, with a settle call and a failed decision call.
        EVENTS + "000002.jsonl": jsonl(
            outcome("2026-09-27T17:57:33.616Z", "U3", outcome="candidate", candidate="C1", answer="claim",
                    probs={"other": 0.0028, "claim": 0.9972}),
            call("2026-09-27T17:57:35.659Z", "U4", "A1: Mutta tuo A-studio-jupakka.", stage="settle"),
            outcome("2026-09-27T17:57:36.058Z", "U4", stage="settle", outcome="none", answer="none",
                    probs={"other": 0.0012, "none": 0.9988}, probability=0.9988),
            call("2026-09-27T17:57:40.000Z", "U5", "A2: Kansa ei ole tyhmää.", elapsed_s=5.0, input_tokens=None,
                 output_tokens=None, cost_usd=0.0, status=503, error="unavailable",
                 error_text="The server is\n overloaded."),
            outcome("2026-09-27T17:57:40.100Z", "U5", outcome="dropped", error="unavailable"),
            # Not the decision model's.
            call("2026-09-27T17:57:41.000Z", "U3", "", stage="fact-finding A"),
        ),
        f"recordings/{OLDER}/events/000001.jsonl": jsonl(
            {"time": "2026-09-20T17:00:00Z", "event": "session start", "record": True},
        ),
    }
    return store


async def test_tail_shows_each_call_with_its_utterance_answer_and_figures(store):
    out: list[str] = []
    assert await tail.tail(store, SESSION, 10, width=100, out=out.append) == 0
    assert lines(*out) == [
        "Session 20260927T175631Z-308317, started 2026-09-27 20:56 Helsinki time (no end event yet). "
        "The decision model's calls:",
        "",
        "20:57:33  U3 decision → candidate C1",
        "  A1: Yleisradio saa 600 miljoonan euron vuotuisen rahoituksen.",
        "  claim 0.997 · other 0.003   1.21 s · 571+13 tokens · $0.000064",
        "",
        "20:57:36  U4 settle → none",
        "  A1: Mutta tuo A-studio-jupakka.",
        "  none 0.999 · other 0.001   1.21 s · 571+13 tokens · $0.000064",
        "",
        "20:57:40  U5 decision → dropped: unavailable",
        "  A2: Kansa ei ole tyhmää.",
        "  5.00 s · $0.000000 · HTTP 503 The server is overloaded.",
    ]


async def test_n_shows_the_last_calls_reading_back_only_the_parts_it_needs(store, monkeypatch):
    monkeypatch.setattr(tail, "BATCH", 1)
    read: list[str] = []
    get = store.get

    async def counted(key: str) -> bytes | None:
        read.append(key)
        return await get(key)

    monkeypatch.setattr(store, "get", counted)
    out: list[str] = []
    await tail.tail(store, SESSION, 1, width=100, out=out.append)
    assert [line for line in lines(*out) if "→" in line] == ["20:57:40  U5 decision → dropped: unavailable"]
    assert read == [EVENTS + "000002.jsonl"]

    # U3's outcome is in part 2 and its call in part 1: both are read.
    read.clear()
    out.clear()
    await tail.tail(store, SESSION, 3, width=100, out=out.append)
    assert [line.split("  ")[1] for line in lines(*out) if "→" in line] == [
        "U3 decision → candidate C1", "U4 settle → none", "U5 decision → dropped: unavailable"]
    assert read == [EVENTS + "000002.jsonl", EVENTS + "000001.jsonl"]


async def test_context_shows_the_prompts_other_fields(store):
    out: list[str] = []
    await tail.tail(store, SESSION, 1, context=True, width=100, out=out.append)
    assert lines(*out)[-4:] == [
        "  place_and_time:",
        "    Espoo. Sunday 27 September 2026, 20:57 (Europe/Helsinki)",
        "  conversation:",
        "    A2: Mainitsit A-studion.",
    ]


async def test_follow_shows_new_calls_until_the_session_ends(store, monkeypatch):
    later = [
        jsonl(call("2026-09-27T17:57:50.000Z", "U6", "A1: Juuri sitähän se tarkoittaa.")),
        b"",  # a poll with nothing new
        jsonl(
            outcome("2026-09-27T17:57:51.000Z", "U6", outcome="repeat", candidate="C1", answer="same as C1",
                    probs={"same as C1": 0.9, "none": 0.1}),
            call("2026-09-27T17:57:52.000Z", "U7", "A2: Kiitos.", stage="settle"),
            {"time": "2026-09-27T17:58:00.000Z", "event": "session end", "listening_s": 88.0},
        ),
    ]
    listed = store.list

    async def growing(prefix: str) -> list[str]:
        if later and (part := later.pop(0)):
            store.objects[EVENTS + f"{len(await listed(EVENTS)) + 1:06d}.jsonl"] = part
        return await listed(prefix)

    monkeypatch.setattr(store, "list", growing)
    out: list[str] = []
    assert await tail.tail(store, SESSION, 0, follow=True, poll_s=0, width=100, out=out.append) == 0
    assert lines(*out)[0].endswith("(following; Ctrl-C stops). The decision model's calls:")
    assert [line for line in lines(*out)[1:] if line and not line.startswith("  ")] == [
        "20:57:51  U6 decision → repeat of C1",
        "20:57:52  U7 settle → …",
        "The session has ended.",
    ]


async def test_follow_stops_when_the_recording_is_deleted(store, monkeypatch):
    listed = store.list
    polls = 0

    async def deleted_after_start(prefix: str) -> list[str]:
        nonlocal polls
        polls += 1
        return await listed(prefix) if polls == 1 else []

    monkeypatch.setattr(store, "list", deleted_after_start)
    out: list[str] = []
    assert await tail.tail(store, SESSION, 0, follow=True, poll_s=0, out=out.append) == 0
    assert out[-1] == "\nThe recording was stopped and deleted."


async def test_an_ended_session_isnt_followed(store):
    store.objects[EVENTS + "000003.jsonl"] = jsonl(
        {"time": "2026-09-27T17:58:00.000Z", "event": "session end", "listening_s": 88.0})
    out: list[str] = []
    assert await tail.tail(store, SESSION, 1, follow=True, poll_s=60, out=out.append) == 0
    assert "(ended)" in out[0] and out[-1] == "\nThe session has ended."


async def test_without_an_id_it_tails_the_newest_session(store):
    out: list[str] = []
    await tail.tail(store, None, 10, out=out.append)
    assert out[0].startswith(f"Session {SESSION},")


async def test_a_session_without_calls_or_a_log(store):
    out: list[str] = []
    await tail.tail(store, OLDER, 10, out=out.append)
    assert out[-1] == "(none yet)"
    with pytest.raises(OwnerError, match="has no event log"):
        await tail.tail(store, "20260101T000000Z-000000", 10, out=out.append)
    with pytest.raises(OwnerError, match="there are no recordings"):
        await tail.tail(MemoryStore(), None, 10, out=out.append)


def test_the_cli_runs_tail(store, monkeypatch, capsys):
    devs: list[bool] = []
    monkeypatch.setattr(owner, "open_store", lambda dev: devs.append(dev) or store)
    assert cli.main(["owner", "tail", SESSION, "-n", "1", "--context", "--dev"]) == 0
    out = capsys.readouterr().out
    assert "U5 decision → dropped: unavailable" in out and "U3 decision" not in out
    assert "  conversation:" in out
    assert cli.main(["owner", "tail", "20260927T175631Z-30831"]) == 1
    assert "carl owner: not a session id" in capsys.readouterr().err
    assert devs == [True, False]
