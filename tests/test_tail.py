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


# --- The candidates' checks ------------------------------------------------------------------

def event(time: str, name: str, /, **fields) -> dict:
    return {"time": f"2026-09-27T{time}Z", "event": name} | fields


def finder_call(time: str, candidate: str, letter: str, text: str = "A1: Yle saa 600 miljoonaa.", **record) -> dict:
    return event(time, "model call", candidate=candidate, utterance="U3", finder=letter, attempt=1,
                 stage=f"fact-finding {letter}", provider="openai", model="gpt-6-luna", prompt="fact-finding",
                 fields={"candidate_kind": "claim", "place_and_time": "Espoo", "conversation": "A2: Mitä?",
                         "candidate": text},
                 elapsed_s=5.5, input_tokens=9000, output_tokens=250, cost_usd=0.01, provider_cost_usd=None,
                 response={"big": "…"}, status=200, error=None) | record


def finding(time: str, candidate: str, letter: str, outcome: str, card: dict | None = None, **fields) -> dict:
    return event(time, "finding", candidate=candidate, finder=letter, after_s=12.0, outcome=outcome,
                 restatement="Ylen rahoitus on 600 miljoonaa euroa vuodessa.", card=card,
                 results=[{"url": "https://yle.fi/a/1", "title": "", "snippet": ""},
                          {"url": "https://yle.fi/a/2", "title": "", "snippet": ""}],
                 searches=["Yle rahoitus"], search_calls=1, model="gpt-6-luna", model_differs=False) | fields


CARD = {"title": "Ylen rahoitus", "fact": "Ylen rahoitus on noin 560 miljoonaa euroa.",
        "source_url": "https://yle.fi/a/1", "source_title": "Yle", "excerpt": "Rahoitus on 560 miljoonaa euroa."}

SHOWN = [
    event("17:57:30.000", "utterance", id="U3", stream=1, speaker="1", text="Yle saa 600 miljoonaa."),
    event("17:57:31.000", "candidate", id="C1", kind="claim", utterance="U3", probability=0.9972,
          card_language={"language": "fi"}),
    event("17:57:31.000", "decision", outcome="candidate", candidate="C1", utterance="U3"),
    finder_call("17:57:37.000", "C1", "A"),
    finding("17:57:37.100", "C1", "A", "claim is wrong", CARD),
    event("17:57:37.500", "download", candidate="C1", finder="A", url=CARD["source_url"], verified=True,
          match="normalised", error=None),
    event("17:57:37.500", "excerpt", candidate="C1", finder="A", method="page", verified=True, reason=None,
          match="normalised"),
    finder_call("17:57:38.000", "C1", "B", provider="perplexity", cost_usd=0.02, provider_cost_usd=0.021),
    finding("17:57:38.100", "C1", "B", "claim is wrong", CARD | {"source_url": "https://reddit.com/r/x"},
            search_calls=2),
    event("17:57:38.100", "blocklisted", candidate="C1", finder="B", url="https://reddit.com/r/x",
          suffix="reddit.com"),
    event("17:57:38.100", "excerpt", candidate="C1", finder="B", method="snippet", verified=False),
    event("17:57:38.100", "findings", candidate="C1", used=["A", "B"], failed={}, missed=[]),
    event("17:57:38.200", "verdict skipped", candidate="C1", finder="B", reason="silent:unverified"),
    event("17:57:38.500", "model call", candidate="C1", utterance="U3", finder="A", stage="fact-checking",
          cost_usd=0.00005, provider_cost_usd=0.00005, response={}),
    event("17:57:38.600", "verdict", candidate="C1", finder="A", answer="supported",
          probs={"not supported": 0.05, "supported": 0.9, "doesn't answer the candidate": 0.05}),
    event("17:57:38.600", "band", candidate="C1", band="hedged", reason="hedged:single-verified", shown="A"),
    event("17:57:38.600", "check", candidate="C1", state="ready", after_s=13.6, band="hedged",
          reason="hedged:single-verified"),
    event("17:57:38.600", "card sent", id="C1", kind="claim", band="hedged", label="Väite", tag="Varauksin",
          title="Ylen rahoitus", fact="Todennäköisesti: Ylen rahoitus on noin 560 miljoonaa euroa."),
    event("17:57:38.700", "card filed", id="C1", late=False),
]


@pytest.fixture
def checked() -> MemoryStore:
    store = MemoryStore()
    store.objects = {
        EVENTS + "000001.jsonl": jsonl(event("17:56:31.934", "session start", record=True), *SHOWN[:5]),
        EVENTS + "000002.jsonl": jsonl(*SHOWN[5:]),
    }
    return store


async def test_a_checks_block_shows_each_finder_the_verdicts_and_the_card(checked):
    out: list[str] = []
    assert await tail.tail(checked, SESSION, 10, checks=True, width=100, out=out.append) == 0
    assert lines(*out) == [
        "Session 20260927T175631Z-308317, started 2026-09-27 20:56 Helsinki time (no end event yet). "
        "The candidates' checks:",
        "",
        "20:57:38  C1 claim → shown (hedged:single-verified), A's card · 13.6 s · $0.031050",
        "  A1: Yle saa 600 miljoonaa.",
        "  flagged: in U3 · claim 0.997 · card language fi",
        "  A  claim is wrong · 12.0 s after the utterance · 5.50 s · 9000+250 tokens · $0.010000 · 1 search,",
        "     2 results",
        "     restated: \"Ylen rahoitus on 600 miljoonaa euroa vuodessa.\"",
        "     searched: \"Yle rahoitus\"",
        "     card: Ylen rahoitus. Ylen rahoitus on noin 560 miljoonaa euroa.",
        "     source: https://yle.fi/a/1",
        "     excerpt: \"Rahoitus on 560 miljoonaa euroa.\"",
        "     verified: ✓ found on the page (normalised)",
        "     verdict: supported 0.900 · not supported 0.050 · doesn't answer the candidate 0.050",
        "  B  claim is wrong · 12.0 s after the utterance · 5.50 s · 9000+250 tokens · $0.021000 · 2",
        "     searches, 2 results",
        "     restated: \"Ylen rahoitus on 600 miljoonaa euroa vuodessa.\"",
        "     searched: \"Yle rahoitus\"",
        "     card: Ylen rahoitus. Ylen rahoitus on noin 560 miljoonaa euroa.",
        "     source: https://reddit.com/r/x",
        "     excerpt: \"Rahoitus on 560 miljoonaa euroa.\"",
        "     verified: ✗ the source is blocklisted (reddit.com)",
        "     verdict: skipped (silent:unverified)",
        "  sent: [Väite · Varauksin] Ylen rahoitus. Todennäköisesti: Ylen rahoitus on noin 560 miljoonaa",
        "        euroa.",
    ]


async def test_checks_context_adds_the_prompt_fields_and_the_search_results(checked):
    out: list[str] = []
    await tail.tail(checked, SESSION, 1, checks=True, context=True, width=100, out=out.append)
    text = lines(*out)
    assert text[text.index("     verified: ✓ found on the page (normalised)") + 2:][:3] == [
        "     results:", "       https://yle.fi/a/1", "       https://yle.fi/a/2"]
    assert text[-6:] == ["  candidate_kind:", "    claim", "  place_and_time:", "    Espoo", "  conversation:",
                         "    A2: Mitä?"]


async def test_checks_read_back_to_the_candidates_start(checked, monkeypatch):
    monkeypatch.setattr(tail, "BATCH", 1)
    out: list[str] = []
    await tail.tail(checked, SESSION, 1, checks=True, width=100, out=out.append)
    assert "  flagged: in U3 · claim 0.997 · card language fi" in lines(*out)


async def test_failures_and_a_check_still_running():
    store = MemoryStore()
    store.objects[EVENTS + "000001.jsonl"] = jsonl(
        event("17:58:00.000", "candidate", id="C2", kind="open question", utterance="U9", probability=0.9,
              card_language={"language": "en"}, repeat_of="C1"),
        finder_call("17:58:10.000", "C2", "B", text="B2: When was it?"),
        finding("17:58:10.100", "C2", "B", "question answered", CARD),
        event("17:58:10.300", "download", candidate="C2", finder="B", url=CARD["source_url"], verified=False,
              error="HTTP 403"),
        event("17:58:10.300", "excerpt", candidate="C2", finder="B", method="page", verified=False,
              reason="download-failed"),
        event("17:58:20.000", "failure", stage="fact-finding A", kind="timeout", candidate="C2",
              error_text="no answer within 30 s"),
        event("17:58:22.000", "findings", candidate="C2", used=["B"], failed={"A": "timeout"}, missed=[]),
        event("17:58:23.000", "verdict", candidate="C2", finder="B", answer=None, probs=None, error="unavailable"),
        event("17:58:23.000", "check", candidate="C2", state="failed", after_s=23.0, stage="fact-checking",
              reason="silent:call-failed", errors={"B": "unavailable"}),
        event("17:59:00.000", "candidate", id="C3", kind="claim", utterance="U12", probability=0.8,
              card_language={"language": "fi"}),
        event("17:59:01.000", "utterance", id="U13", stream=1, speaker="1", text="Joo."),
    )
    out: list[str] = []
    await tail.tail(store, SESSION, 10, checks=True, width=100, out=out.append)
    text = lines(*out)
    assert text[2:5] == [
        "20:58:23  C2 open question → failed in fact-checking: silent:call-failed · 23.0 s · $0.010000",
        "  B2: When was it?",
        "  flagged: in U9 · open question 0.900 · card language en · repeat of failed C1",
    ]
    assert "  A  failed: timeout (no answer within 30 s)" in text
    assert "     verified: ✗ not found on the page: download-failed, HTTP 403" in text
    assert "     verdict: failed: unavailable" in text
    assert text[-2:] == ["20:59:00  C3 claim → still being checked", "  flagged: in U12 · claim 0.800 · card language fi"]


async def test_following_checks_shows_what_happens_after_a_block(checked, monkeypatch):
    # Following from the first part: C1's block comes with the second.
    later = [
        checked.objects.pop(EVENTS + "000002.jsonl"),
        jsonl(finding("17:57:50.000", "C1", "B", "claim is right", after_s=24.4),
              event("17:57:55.000", "card withdrawn", id="C1", reason="silent:settled", age_s=25.0),
              event("17:57:55.000", "check", candidate="C1", state="dropped", after_s=25.0, reason="silent:settled",
                    settled_by="U5"),
              event("17:57:56.000", "failure", stage="fact-checking", kind="timeout", candidate="C1"),
              event("17:57:57.000", "verdict", candidate="C1", finder="B", answer="supported", probs={})),
        jsonl(event("17:58:00.000", "session end", listening_s=88.0)),
    ]
    listed = checked.list
    polls = 0

    async def growing(prefix: str) -> list[str]:
        nonlocal polls
        polls += 1
        if polls > 1 and later:  # a new part at each poll
            checked.objects[EVENTS + f"{len(await listed(EVENTS)) + 1:06d}.jsonl"] = later.pop(0)
        return await listed(prefix)

    monkeypatch.setattr(checked, "list", growing)
    out: list[str] = []
    assert await tail.tail(checked, SESSION, 0, checks=True, follow=True, poll_s=0, width=100, out=out.append) == 0
    heads = [line for line in lines(*out)[1:] if line and not line.startswith("  ")]
    assert heads == [
        "20:57:38  C1 claim → shown (hedged:single-verified), A's card · 13.6 s · $0.031050",
        "20:57:50  C1 late answer from B: claim is right, 24.4 s after the utterance",
        "20:57:55  C1 card withdrawn (silent:settled)",
        "20:57:55  C1 → dropped (silent:settled, settled by U5)",
        "20:57:56  C1 fact-checking failed: timeout",
        "The session has ended.",
    ]


async def test_a_finding_after_the_check_ended_is_marked_too_late():
    store = MemoryStore()
    store.objects[EVENTS + "000001.jsonl"] = jsonl(
        event("17:58:00.000", "candidate", id="C4", kind="claim", utterance="U9", probability=1.0,
              card_language={"language": "fi"}),
        finding("17:58:40.000", "C4", "B", "not found"),
        event("17:58:57.000", "check", candidate="C4", state="failed", after_s=60.0, stage="fact-finding",
              kind="timeout", waiting_on=["fact-finding A"]),
        event("17:59:00.000", "findings", candidate="C4", used=["B"], failed={}, missed=["A"]),
        finding("17:59:03.000", "C4", "A", "claim is right", after_s=66.7),
    )
    out: list[str] = []
    await tail.tail(store, SESSION, 1, checks=True, width=120, out=out.append)
    text = lines(*out)
    assert text[2] == "20:58:57  C4 claim → failed in fact-finding: timeout, waiting on fact-finding A · 60.0 s"
    assert "  A  claim is right · 66.7 s after the utterance · too late, not used · 1 search, 2 results" in text
    assert "  B  not found · 12.0 s after the utterance · 1 search, 2 results" in text


async def test_a_block_ends_with_what_happened_after_its_check(checked):
    checked.objects[EVENTS + "000003.jsonl"] = jsonl(
        event("17:57:55.000", "card withdrawn", id="C1", reason="silent:settled", age_s=25.0),
        event("17:57:55.000", "check", candidate="C1", state="dropped", after_s=25.0, reason="silent:settled",
              settled_by="U5"),
    )
    out: list[str] = []
    await tail.tail(checked, SESSION, 1, checks=True, width=100, out=out.append)
    assert lines(*out)[-2:] == ["  20:57:55  card withdrawn (silent:settled)",
                                "  20:57:55  → dropped (silent:settled, settled by U5)"]


def test_the_cli_runs_tail_checks(checked, monkeypatch, capsys):
    monkeypatch.setattr(owner, "open_store", lambda dev: checked)
    assert cli.main(["owner", "tail", SESSION, "--checks", "-n", "1"]) == 0
    out = capsys.readouterr().out
    assert "C1 claim → shown (hedged:single-verified)" in out and "The candidates' checks:" in out
