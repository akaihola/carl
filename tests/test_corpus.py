import json
from datetime import UTC, datetime, timedelta

import pytest

from carl import cli, corpus, owner
from carl.corpus import CorpusError, Folded, Text
from carl.owner import Kept, OwnerError
from carl.storage import MemoryStore

ID = "20260927T160000Z-a1b2c3"
OTHER = "20260920T170000Z-0f0f0f"
T0 = datetime(2026, 9, 27, 16, 0, tzinfo=UTC)  # 19:00 in Helsinki

EINSTEIN = {"title": "Einstein ja matematiikka",
            "fact": "Einstein ei reputtanut matematiikkaa: hän hallitsi integraalilaskennan ennen 15 ikävuotta.",
            "source_url": "https://fi.wikipedia.org/wiki/Albert_Einstein",
            "source_title": "Albert Einstein – Wikipedia",
            "excerpt": "Einstein hallitsi differentiaali- ja integraalilaskennan jo ennen 15 vuoden ikää."}
CASABLANCA = {"title": "Casablanca", "fact": "Michael Curtiz directed Casablanca (1942).",
              "source_url": "https://en.wikipedia.org/wiki/Casablanca_(film)", "source_title": "Casablanca (film)",
              "excerpt": "Casablanca is a 1942 American romantic drama film directed by Michael Curtiz."}
KEMIJOKI = {"title": "Suomen pisin joki", "fact": "Suomen pisin joki on Kemijoki.",
            "source_url": "https://fi.wikipedia.org/wiki/Kemijoki", "source_title": "Kemijoki",
            "excerpt": "Kemijoki on…"}
KALLIO = {"neighbourhood": "Kallio", "city": "Helsinki", "region": "Uusimaa", "country": "Suomi / Finland",
          "country_code": "FI"}
TOOLO = KALLIO | {"neighbourhood": "Töölö"}
HELSINKI = KALLIO | {"neighbourhood": None}
COORDINATES = ("60.1841", "24.9497", "60.18", "24.95", "Fleminginkatu")


def at(seconds: float) -> str:
    return (T0 + timedelta(seconds=seconds)).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class Log:
    """A recording's event log, as the server writes it, built in order.
    Times are seconds from Start."""

    def __init__(self, session: str = ID) -> None:
        self.session = session
        self.events: list[dict] = []
        self.opened: dict[int, float] = {}
        self.utterances = 0

    def add(self, t: float, event: str, **fields) -> "Log":
        self.events.append({"time": at(t), "event": event, **fields})
        return self

    def start(self, **changes) -> "Log":
        fields = {"session": self.session, "record": True,
                  "disclosure": {"text": "Tämä on testi.", "confirmed_at": at(0)}, "mic": {"autoGainControl": True},
                  "timezone": "Europe/Helsinki", "location": True, "commit": "abc1234",
                  "config": {"version": "3be91c0a", "text": "# Carl's config file"}, "prompts": {}} | changes
        return self.add(0, "session start", **fields)

    def open(self, t: float, stream: int) -> "Log":
        self.opened[stream] = t
        return self.add(t, "stt open", stream=stream)

    def say(self, t: float, stream: int, speaker: str, text: str, start_ms: int | None = None,
            logged: float | None = None) -> str:
        """An utterance whose first word was said `t` seconds after Start;
        `start_ms` on the stream's clock when it isn't wall time."""
        self.utterances += 1
        uid = f"U{self.utterances}"
        start_ms = round((t - self.opened[stream]) * 1000) if start_ms is None else start_ms
        end_ms = start_ms + 400 * len(text.split())
        self.add(t + (end_ms - start_ms) / 1000 + 0.5 if logged is None else logged, "utterance", id=uid,
                 stream=stream, speaker=speaker, text=text, start_ms=start_ms, end_ms=end_ms,
                 words=[{"text": w, "start_ms": start_ms + 400 * i} for i, w in enumerate(text.split())])
        return uid

    def decide(self, t: float, uid: str, outcome: str = "none", **fields) -> None:
        self.add(t, "model call", utterance=uid, stage="decision", cost_usd=0.00002, provider="openai")
        self.add(t, "decision", utterance=uid, outcome=outcome, answer=outcome, probs=None, **fields)

    def flag(self, t: float, uid: str, cid: str, kind: str = "claim", **fields) -> None:
        self.add(t, "model call", utterance=uid, stage="decision", cost_usd=0.00002, provider="openai")
        self.add(t, "candidate", id=cid, kind=kind, utterance=uid, probability=0.9,
                 card_language={"language": "fi", "rule": "most words", "window_words": {"fi": 30}, "own_words": {}},
                 **fields)
        self.add(t, "decision", utterance=uid, outcome="candidate", candidate=cid, answer=kind, probs=None)

    def finding(self, t: float, cid: str, finder: str, outcome: str, restatement: str, card: dict | None = None):
        self.add(t, "model call", candidate=cid, finder=finder, stage=f"fact-finding {finder}", cost_usd=0.01)
        self.add(t, "finding", candidate=cid, finder=finder, after_s=5.0, outcome=outcome, restatement=restatement,
                 card=card, results=[], searches=["haku"], search_calls=1, model="m", model_differs=False,
                 source_in_results=True)

    def verdict(self, t: float, cid: str, finder: str, p: float) -> None:
        self.add(t, "verdict", candidate=cid, finder=finder, answer="supported",
                 probs={"supported": p, "not supported": 1 - p, "doesn't answer the candidate": 0.0})

    def card(self, t: float, cid: str, band: str, card: dict, age_s: float, fact: str | None = None) -> None:
        self.add(t, "card sent", page=True, id=cid, kind="claim", band=band, language="fi", label="Väite",
                 tag=None if band == "plain" else "Varauksin", title=card["title"], fact=fact or card["fact"],
                 source={"url": card["source_url"], "title": card["source_title"]}, utterance_time=at(t - age_s),
                 age_s=age_s)

    def end(self, t: float, listening_s: float, cost_usd: float) -> "Log":
        return self.add(t, "session end", reason="end", listening_s=listening_s, cost_usd=cost_usd, utterances=10,
                        cards=2)


def dinner() -> Log:
    """A dinner: small talk and a skipped backchannel, a plain card, a late
    hedged card, a repeat, a silent candidate, a Pause, a failed candidate,
    a speech-to-text gap, a dropped page connection and a move across town,
    with events Carl doesn't know along the way."""
    log = Log().start()
    log.add(0.3, "location fix", fix={"lat": 60.1841, "lon": 24.9497, "accuracy_m": 20, "time": at(0.3)},
            level="full")
    log.add(1.2, "geocoder", lat=60.184, lon=24.95, zoom=14, source="nominatim", elapsed_s=0.4,
            response={"display_name": "Fleminginkatu 1, Kallio, Helsinki", "address": {"road": "Fleminginkatu"}})
    log.add(1.2, "place", place=KALLIO)
    log.open(0.5, 1)
    log.add(1.0, "stt", stream=1, raw={"tokens": []})
    u = log.say(4, 1, "1", "No niin, onks kaikilla juotavaa?")
    log.decide(6, u)
    u = log.say(7, 1, "2", "Joo.")
    log.add(8, "decision skipped", utterance=u)

    # C1: a plain card, shown 6.8 s after its utterance.
    u = log.say(271, 1, "2", "Einstein muuten reputti matikan koulussa, se on ihan tunnettu juttu.")
    log.flag(277, u, "C1")
    log.finding(280, "C1", "A", "claim is wrong", "Einstein failed mathematics at school.", EINSTEIN)
    log.add(281, "download", candidate="C1", finder="A", url=EINSTEIN["source_url"], cost_usd=0.0, verified=True)
    log.add(281, "excerpt", candidate="C1", finder="A", method="page", verified=True, reason=None, match="normalised")
    log.finding(281, "C1", "B", "claim is wrong", "Albert Einstein reputti matematiikan koulussa.", EINSTEIN)
    log.add(281, "excerpt", candidate="C1", finder="B", method="snippet", verified=False)
    log.add(281, "findings", candidate="C1", used=["A", "B"], failed={}, missed=[])
    log.verdict(282, "C1", "A", 0.96)
    log.verdict(282, "C1", "B", 0.91)
    log.add(282, "agreement", candidate="C1", answer="same fact",
            probs={"same fact": 0.93, "compatible but different": 0.05, "contradict": 0.02})
    log.add(282, "band", candidate="C1", band="plain", reason="plain:agreed", shown="A")
    log.add(282, "check", candidate="C1", state="ready", after_s=6.1, band="plain", reason="plain:agreed")
    log.card(282, "C1", "plain", EINSTEIN, 6.1)
    log.add(282.7, "card shown", id="C1", at=at(282.6), received=at(282.7), age_s=6.8, state="on screen")
    u = log.say(276.5, 1, "3", "Oikeesti?")
    log.add(278, "decision skipped", utterance=u)

    # C2: an open question whose hedged card was late.
    u = log.say(432, 1, "1", "Who directed Casablanca, by the way?")
    log.flag(435, u, "C2", kind="open question")
    log.finding(440, "C2", "A", "question answered", "Who directed the film Casablanca (1942)?", CASABLANCA)
    log.add(441, "excerpt", candidate="C2", finder="A", method="page", verified=True, reason=None, match="normalised")
    log.finding(441, "C2", "B", "not found", "Kuka ohjasi Casablancan?")
    log.add(441, "findings", candidate="C2", used=["A", "B"], failed={}, missed=[])
    log.verdict(450, "C2", "A", 0.88)
    log.add(450, "band", candidate="C2", band="hedged", reason="hedged:single-verified", shown="A")
    log.add(450, "check", candidate="C2", state="ready", after_s=23.1, band="hedged", reason="hedged:single-verified")
    log.card(456.6, "C2", "hedged", CASABLANCA, 23.1, fact="Probably: Michael Curtiz directed Casablanca (1942).")
    log.add(457, "card filed", id="C2", at=at(457), received=at(457), late=True, age_s=23.5, state="card history")
    log.add(458, "card filed", id="C1", at=at(458), received=at(458), late=False, age_s=187, state="card history")

    # A repeat of C1.
    u = log.say(700, 1, "2", "But he did fail maths, didn't he?")
    log.add(703, "repeat", utterance=u, candidate="C1", probability=0.8123)
    log.decide(703, u, "repeat", candidate="C1")

    # C3: silent, a contradiction.
    u = log.say(1082, 1, "4", "Suomen pisin joki on Kemijoki.")
    log.flag(1085, u, "C3")
    log.finding(1090, "C3", "A", "claim is right", "Suomen pisin joki on Kemijoki.")
    log.finding(1091, "C3", "B", "claim is wrong", "Kemijoki on Suomen pisin joki.", KEMIJOKI)
    log.add(1091, "excerpt", candidate="C3", finder="B", method="snippet", verified=True)
    log.add(1091, "findings", candidate="C3", used=["A", "B"], failed={}, missed=[])
    log.add(1091, "verdict skipped", candidate="C3", finder="B", reason="silent:contradiction")
    log.add(1091, "band", candidate="C3", band="none", reason="silent:contradiction", shown=None)
    log.add(1091, "check", candidate="C3", state="silent", after_s=9.0, reason="silent:contradiction")

    # A Pause: the finalise gives one more utterance, logged after the pause.
    log.add(1270, "pause")
    log.add(1270, "audio", key="audio/000021.pcm", start=at(1230), bytes=1280000)
    log.add(1270.1, "stt finalize", stream=1, silence_ms=200)
    log.say(1268, 1, "1", "No mutta.", logged=1270.2)
    log.add(1270.3, "stt closed", stream=1)
    log.add(1650, "resume")
    log.open(1650.2, 2)
    log.add(2000, "place", place=HELSINKI)  # a poorer fix: the same town

    # C4: failed at fact-finding.
    u = log.say(1682, 2, "1", "Tampere on Pohjoismaiden suurin sisämaakaupunki.")
    log.flag(1685, u, "C4")
    log.add(1700, "model call", candidate="C4", finder="A", stage="fact-finding A", error="timeout", estimated=True)
    log.add(1700, "findings", candidate="C4", used=[], failed={"A": "timeout", "B": "timeout"}, missed=[])
    log.add(1700, "failure", stage="fact-finding A", kind="timeout", candidate="C4")
    log.add(1700, "check", candidate="C4", state="failed", after_s=18.0, stage="fact-finding",
            errors={"A": "timeout", "B": "timeout"})
    log.add(3000, "location fix", fix={"lat": 60.1841, "lon": 24.9197, "accuracy_m": 15, "time": at(3000)})
    log.add(3000, "place", place=TOOLO)

    # A speech-to-text gap, then a dropped page connection on stream 3.
    log.add(3730, "stt failed", stream=2, kind="unavailable", detail="503")
    log.open(3770, 3)
    u = log.say(3800, 3, "1", "Sibelius sävelsi kahdeksan sinfoniaa.")
    log.decide(3803, u)
    log.add(4000, "page gone")
    log.add(4000.1, "stt finalize", stream=3, silence_ms=200)
    log.add(4060, "page back")
    log.add(4061, "some later step's event", candidate=["not", "a", "string"], utterance=None)
    # Stream 3's clock missed the 60 s away, less the 0.2 s of silence.
    log.say(4100, 3, "2", "Mennäänkö jo?", start_ms=round((4000 - 3770 + 0.2 + 40) * 1000))
    log.end(4200, listening_s=3814.4, cost_usd=0.81234)
    log.add(4200.001, "audio", key="audio/000070.pcm", start=at(4100), bytes=64000)
    return log


@pytest.fixture
def log() -> Log:
    return dinner()


@pytest.fixture
def md(log) -> str:
    return corpus.generate(log.events)


def lines(md: str) -> list[str]:
    return md.splitlines()


def block(md: str, first: str) -> str:
    """The block whose first line is `first`, without its fences."""
    all_lines = lines(md)
    i = all_lines.index(first)
    return "\n".join(all_lines[i:all_lines.index("```", i)])


def fields(md: str, first: str) -> dict:
    return corpus.load(block(md, first).splitlines())


def replace(md: str, old: str, new: str) -> str:
    assert md.count(old) == 1, old
    return md.replace(old, new)


# --- generate --------------------------------------------------------------------------------


def test_the_header(md):
    assert lines(md)[0] == "# Recording session 2026-09-27 19:00 (Europe/Helsinki)"
    header = block(md, "session: " + ID)
    assert header.splitlines() == [
        f"session: {ID}",
        'place: ["Kallio, Helsinki", "Töölö, Helsinki"]',
        "listening: 1h03m",
        "config: config.toml@3be91c0a",
        "cost_usd: 0.8123",
        "status: not started     # not started | in progress | done",
        "same_speaker: []        # e.g. [[A2, B1]]",
        "format: 1",
    ]
    assert lines(md)[2] == "```yaml carl-session"


def test_places_are_neighbourhood_and_town_never_coordinates(md):
    assert fields(md, "session: " + ID)["place"] == ["Kallio, Helsinki", "Töölö, Helsinki"]
    for text in COORDINATES + ("Uusimaa", "Suomi", "FI"):
        assert text not in md


def test_a_place_found_first_by_town_only_gets_its_neighbourhood():
    log = Log().start()
    log.add(1, "place", place=HELSINKI).add(2, "place", place=KALLIO).add(3, "place", place=None)
    log.add(4, "place", place={"neighbourhood": None, "city": None, "region": "Lappi", "country": "Suomi"})
    assert fields(corpus.generate(log.events), "session: " + ID)["place"] == ["Kallio, Helsinki", "Lappi"]


@pytest.mark.parametrize("change, why", [
    ({"location": False}, "location off"),
    ({}, "no place known"),
])
def test_no_place_says_why(change, why):
    header = block(corpus.generate(Log().start(**change).events), "session: " + ID)
    assert f"place: []               # {why}" in header


def test_a_denied_location_says_so():
    log = Log().start().add(1, "location denied")
    assert "# location denied" in block(corpus.generate(log.events), "session: " + ID)


def test_the_transcript_counts_from_start_with_labels_unique_across_streams(md):
    said = [line for line in lines(md) if line.startswith("**")]
    assert said == [
        "**A1** · 00:00:04 · No niin, onks kaikilla juotavaa? \\",
        "**A2** · 00:00:07 · Joo. \\",  # skipped backchannel is kept
        "**A2** · 00:04:31 · Einstein muuten reputti matikan koulussa, se on ihan tunnettu juttu.",
        "**A3** · 00:04:36 · Oikeesti? \\",
        "**A1** · 00:07:12 · Who directed Casablanca, by the way?",
        "**A2** · 00:11:40 · But he did fail maths, didn't he?",
        "**A4** · 00:18:02 · Suomen pisin joki on Kemijoki.",
        "**A1** · 00:21:08 · No mutta.",
        "**B1** · 00:28:02 · Tampere on Pohjoismaiden suurin sisämaakaupunki.",
        "**C1** · 01:03:20 · Sibelius sävelsi kahdeksan sinfoniaa.",
        "**C2** · 01:08:20 · Mennäänkö jo?",  # its stream's clock set right after the page came back
    ]


def test_a_run_of_lines_breaks_after_each_but_its_last(md):
    """` \\` is Markdown's hard line break: a run shows one line each, not one paragraph."""
    text = lines(md)
    for i, line in enumerate(text):
        if line.startswith("**"):
            assert line.endswith(" \\") == (i + 1 < len(text) and text[i + 1].startswith("**")), line
    doc = corpus.parse(md)
    assert [s.text for s in doc.said[:2]] == ["No niin, onks kaikilla juotavaa?", "Joo."]
    assert doc.said[3].text == "Oikeesti?"


def test_a_line_with_no_text_still_breaks():
    log = Log().start()
    log.open(0.5, 1)
    log.say(1, 1, "1", "")
    log.say(3, 1, "2", "Hei.")
    md = corpus.generate(log.events)
    assert "**A1** · 00:00:01 · \\\n**A2** · 00:00:03 · Hei.\n" in md
    assert [(s.label, s.text) for s in corpus.parse(md).said] == [("A1", ""), ("A2", "Hei.")]


def test_markers_sit_at_the_pause_and_the_gaps(md):
    text = lines(md)
    paused = text.index("*— paused 00:21:10–00:27:30 —*")
    assert text[paused - 2] == "**A1** · 00:21:08 · No mutta."  # finalised after the pause, said before it
    assert text[paused + 2].startswith("**B1** · 00:28:02")
    stt_gap = text.index("*— gap 01:02:10–01:02:50 —*")
    page_gap = text.index("*— gap 01:06:40–01:07:40 —*")
    assert text[stt_gap + 2].startswith("**C1** · 01:03:20") and text[page_gap + 2].startswith("**C2** · 01:08:20")
    assert text[paused - 1] == text[paused + 1] == ""


def test_a_plain_card(md):
    assert block(md, "id: C1") == "\n".join([
        "id: C1",
        "kind: claim",
        "shown: plain",
        "late: false",
        "check_time_s: 6.8",
        'title: "Einstein ja matematiikka"',
        'card: "Einstein ei reputtanut matematiikkaa: hän hallitsi integraalilaskennan ennen 15 ikävuotta."',
        "source: https://fi.wikipedia.org/wiki/Albert_Einstein",
        "restated:",
        "  A: >",
        "    Einstein failed mathematics at school.",
        "  B: >",
        "    Albert Einstein reputti matematiikan koulussa.",
        "verdict: {A: wrong, B: wrong, same_fact: 0.93, supported: [0.96, 0.91], verified: [page, no], "
        "reason: plain:agreed}",
        "mark:                   # deserved | wrong | nitpick | opinion | contested | already settled | not checkable",
        "note:",
    ])


def test_each_block_comes_right_after_its_utterance(md):
    text = lines(md)
    for said, first in [("**A2** · 00:04:31", "id: C1"), ("**A1** · 00:07:12", "id: C2"),
                        ("**A2** · 00:11:40", "repeat_of: C1"), ("**A4** · 00:18:02", "id: C3"),
                        ("**B1** · 00:28:02", "id: C4")]:
        i = text.index(first)
        assert text[i - 1] == "```yaml carl-candidate" and text[i - 2] == ""
        assert text[i - 3].startswith(said)


def test_a_late_hedged_card(md):
    c2 = fields(md, "id: C2")
    assert c2 == {
        "id": "C2", "kind": "open question", "shown": "hedged", "late": True, "check_time_s": 23.1,
        "title": "Casablanca", "card": "Probably: Michael Curtiz directed Casablanca (1942).",
        "source": "https://en.wikipedia.org/wiki/Casablanca_(film)",
        "restated": {"A": "Who directed the film Casablanca (1942)?", "B": "Kuka ohjasi Casablancan?"},
        "verdict": {"A": "answered", "B": "not found", "supported": [0.88, None], "verified": ["page", None],
                    "reason": "hedged:single-verified"},
        "mark": None, "note": None,
    }


def test_a_repeat(md):
    assert block(md, "repeat_of: C1") == "\n".join([
        "repeat_of: C1",
        "p: 0.81",
        "mark:                   # ok | bad match",
        "note:",
    ])


def test_a_silent_candidate_and_a_failed_one(md):
    c3 = fields(md, "id: C3")
    assert c3["shown"] == "no" and "card" not in c3 and "late" not in c3 and "check_time_s" not in c3
    assert c3["verdict"] == {"A": "right", "B": "wrong", "verified": [None, "snippet"],
                             "reason": "silent:contradiction"}
    assert "mark:                   # ok | should show" in block(md, "id: C3")
    c4 = fields(md, "id: C4")
    assert c4 == {"id": "C4", "kind": "claim", "shown": "no", "state": "failed at fact-finding",
                  "verdict": {"A": "failed:timeout", "B": "failed:timeout"}, "mark": None, "note": None}


def test_generate_is_a_pure_function_of_the_log(log):
    assert corpus.generate(log.events) == corpus.generate(json.loads(json.dumps(log.events)))


def test_a_recording_made_before_the_checks_has_fewer_blocks():
    """Step 2: the transcript only. Step 3: candidates and repeats, never checked."""
    log = Log().start()
    log.open(0.5, 1)
    u1 = log.say(10, 1, "1", "Helsinki perustettiin 1550.")
    log.add(20, "pause").add(30, "resume")
    log.open(30.2, 2)
    log.say(40, 2, "1", "Joo.")
    log.end(50, 40.0, 0.001)
    md = corpus.generate(log.events)
    assert "carl-candidate" not in md and md.count("**") == 4
    assert "*— paused 00:00:20–00:00:30 —*" in md

    log.events.insert(-1, {"time": at(12), "event": "candidate", "id": "C1", "kind": "claim", "utterance": u1})
    log.events.insert(-1, {"time": at(41), "event": "repeat", "utterance": "U2", "candidate": "C1",
                           "probability": 0.7})
    md = corpus.generate(log.events)
    assert fields(md, "id: C1") == {"id": "C1", "kind": "claim", "shown": "no", "mark": None, "note": None}
    assert fields(md, "repeat_of: C1") == {"repeat_of": "C1", "p": 0.7, "mark": None, "note": None}
    assert corpus.check(md, log.events) == []


def test_a_settled_candidate_whose_card_was_withdrawn():
    log = Log().start()
    log.open(0.5, 1)
    u1 = log.say(300, 1, "2", "Helsingin olympialaiset olivat 1956.")
    log.flag(301, u1, "C1")
    log.finding(305, "C1", "B", "claim is wrong", "Helsingin olympialaiset olivat vuonna 1956.", EINSTEIN)
    log.add(306, "band", candidate="C1", band="hedged", reason="hedged:single-verified", shown="B")
    log.add(306, "check", candidate="C1", state="ready", after_s=6, band="hedged", reason="hedged:single-verified")
    log.card(306, "C1", "hedged", EINSTEIN, 6)
    u2 = log.say(308, 1, "3", "Ei vaan 1952.")
    log.add(309, "settle", utterance=u2, outcome="settles C1", candidate="C1", applied=True)
    log.add(309, "band", candidate="C1", band="none", reason="silent:settled", shown=None, settled_by=u2)
    log.add(309, "check", candidate="C1", state="dropped", after_s=9, reason="silent:settled", settled_by=u2)
    log.add(309, "card withdrawn", id="C1", age_s=9, reason="silent:settled")
    c1 = fields(corpus.generate(log.events), "id: C1")
    assert c1["shown"] == "no" and c1["state"] == "dropped" and c1["settled_by"] == "A3 · 00:05:08"
    assert c1["verdict"] == {"B": "wrong", "reason": "silent:settled"}


def test_a_repeat_of_a_failed_candidate_is_a_candidate_of_its_own():
    log = Log().start()
    log.open(0.5, 1)
    u1 = log.say(60, 1, "1", "Tampere on suurin sisämaakaupunki.")
    log.flag(61, u1, "C1")
    log.add(70, "check", candidate="C1", state="failed", stage="fact-finding", kind="overload")
    u2 = log.say(90, 1, "2", "Tampere on siis Pohjoismaiden suurin sisämaakaupunki.")
    log.add(91, "repeat", utterance=u2, candidate="C1", probability=0.77)
    log.flag(91, u2, "C2", repeat_of="C1")
    md = corpus.generate(log.events)
    assert fields(md, "id: C1")["state"] == "failed at fact-finding (overload)"
    c2 = fields(md, "id: C2")
    assert (c2["repeat_of"], c2["p"], c2["shown"]) == ("C1", 0.77, "no")
    assert md.count("repeat_of:") == 1  # no repeat block of its own
    assert corpus.check(md, log.events) == []


def test_unknown_events_and_missing_fields_are_passed_over():
    log = Log().start(config="…", timezone="Mars/Olympus")
    log.open(0.5, 1)
    log.events.append({"event": "no time at all"})
    log.events.append({"time": "2026-09-27T16:00:04", "event": "stt", "stream": 1})  # no zone: UTC
    log.events.append("not an event")
    u = log.say(5, 1, "1", "Kuu on juustoa.")
    log.add(6, "candidate", id="C1", utterance=u)  # no kind
    log.add(7, "findings", candidate="C1", used=None, failed="?", missed=3)
    log.add(7, "finding", candidate="C1", finder="A")
    log.add(8, "verdict", candidate="C1", finder="A", probs="?", error="timeout")
    log.add(8, "agreement", candidate="C1", answer="contradict", probs=None)
    log.add(9, "card sent", id="C1")
    log.add(9, "card shown", id="C1", age_s="soon")
    log.add(9, "utterance", id="U9", stream="x", speaker=None, text=None)
    md = corpus.generate(log.events)
    assert md.startswith("# Recording session 2026-09-27 19:00 (Europe/Helsinki)")
    assert "config: config.toml\n" not in md and "config:\n" in md
    assert fields(md, "id: C1") == {"id": "C1", "kind": None, "shown": "yes", "title": None, "card": None,
                                    "source": None, "late": False, "state": "unfinished",
                                    "verdict": {"A": None, "same_fact": "contradict",
                                                "supported": ["failed:timeout", None]},
                                    "mark": None, "note": None}
    assert "** · 00:00:" in md  # an utterance with no stream or speaker still has its line
    assert corpus.check(md, log.events) == []


def test_a_log_without_its_end_counts_listening_and_leaves_the_cost_empty():
    log = Log().start()
    log.open(0.5, 1)
    log.say(5, 1, "1", "Hei.")
    log.add(100, "pause").add(200, "resume").add(300, "stt open", stream=2)
    header = block(corpus.generate(log.events), "session: " + ID)
    assert "listening: 3m20s        # no end event: counted from the log" in header
    assert "cost_usd:               # no end event" in header


def test_a_stopped_recording_leaves_nothing_to_generate():
    with pytest.raises(CorpusError, match="empty"):
        corpus.generate([])
    with pytest.raises(CorpusError, match="no `session start`"):
        corpus.generate([{"time": at(1), "event": "utterance", "id": "U1", "text": "Hei."}])


# --- check -----------------------------------------------------------------------------------


def test_a_fresh_file_passes(md, log):
    assert corpus.check(md, log.events) == []
    assert corpus.check(md, None) == []


def test_text_fixes_pass(md, log):
    fixed = replace(md, "reputti matikan koulussa", "reputti matikan kokeessa")
    assert corpus.check(fixed, log.events) == []


def mark(md: str, first: str, value: str, field: str = "mark") -> str:
    """Set a block's `mark` (or `field`)."""
    all_lines = lines(md)
    i = all_lines.index(first)
    j = next(k for k in range(i, len(all_lines)) if all_lines[k].startswith(f"{field}:"))
    all_lines[j] = f"{field}: {value}"
    return "\n".join(all_lines) + "\n"


def marked(md: str) -> str:
    for first, value in [("id: C1", "deserved"), ("id: C2", "already settled"), ("repeat_of: C1", "bad match"),
                         ("id: C3", "should show"), ("id: C4", "ok")]:
        md = mark(md, first, value)
    return md


def test_known_marks_pass(md, log):
    assert corpus.check(marked(md), log.events) == []


@pytest.mark.parametrize("first, value, expected", [
    ("id: C1", "great", "C1 has the mark great; a shown card's mark is one of: deserved, wrong"),
    ("id: C1", "ok", "C1 has the mark ok; a shown card's"),
    ("id: C3", "deserved", "C3 has the mark deserved; a candidate with no card's mark is one of: ok, should show"),
    ("repeat_of: C1", "deserved", "the repeat of C1 has the mark deserved; a repeat's mark is one of: ok, bad match"),
    ("id: C2", "1", "C2 has the mark 1;"),
])
def test_unknown_marks_are_rejected(md, log, first, value, expected):
    problems = corpus.check(mark(md, first, value), log.events)
    assert len(problems) == 1 and expected in problems[0] and problems[0].startswith("line ")


def test_a_changed_candidate_id_is_rejected(md, log):
    problems = corpus.check(replace(md, "id: C2", "id: C9"), log.events)
    assert any("C9 isn't a candidate of this recording" in p for p in problems)
    assert "C2 is missing: its block comes after **A1** · 00:07:12" in problems


def test_a_missing_or_moved_block_is_rejected(md, log):
    c3 = "```yaml carl-candidate\n" + block(md, "id: C3") + "\n```\n"
    assert corpus.check(replace(md, c3, ""), log.events) == ["C3 is missing: its block comes after **A4** · 00:18:02"]
    after_pause = "**A1** · 00:21:08 · No mutta.\n"
    moved = replace(replace(md, c3, ""), after_pause, after_pause + "\n" + c3)
    problems = corpus.check(moved, log.events)
    assert len(problems) == 1 and "C3's block should come after **A4** · 00:18:02" in problems[0]
    doubled = replace(md, c3, c3 + "\n" + c3)
    assert any("a second block for C3" in p for p in corpus.check(doubled, log.events))


def test_repeats_must_stay(md, log):
    assert corpus.check(replace(md, "repeat_of: C1", "repeat_of: C2"), log.events)[0].endswith(
        "repeat_of C2 should be C1")
    repeat = "```yaml carl-candidate\n" + block(md, "repeat_of: C1") + "\n```\n"
    assert corpus.check(replace(md, repeat, ""), log.events) == [
        "the repeat of C1 is missing: its block comes after **A2** · 00:11:40"]
    extra = replace(md, "**A3** · 00:04:36 · Oikeesti? \\\n", "**A3** · 00:04:36 · Oikeesti?\n\n" + repeat)
    assert any("the recording has no repeat here" in p for p in corpus.check(extra, log.events))
    nameless = replace(md, "repeat_of: C1\np: 0.81", "p: 0.81")
    assert any("neither an id nor repeat_of" in p for p in corpus.check(nameless, log.events))


@pytest.mark.parametrize("old, new, expected", [
    ("**A2** · 00:04:31", "**A2** · 00:04:32", "**A2** · 00:04:32 should be **A2** · 00:04:31"),
    ("**A2** · 00:04:31", "**A5** · 00:04:31", "**A5** · 00:04:31 should be **A2** · 00:04:31"),
    ("**A3** · 00:04:36 · Oikeesti? \\\n", "", "the line **A3** · 00:04:36 is missing before here"),
    ("**A3** · 00:04:36 · Oikeesti? \\\n",
     "**A3** · 00:04:36 · Oikeesti? \\\n**A1** · 00:05:00 · Ihan totta. \\\n",
     "**A1** · 00:05:00 isn't in the recording"),
])
def test_changed_times_labels_and_lines_are_rejected(md, log, old, new, expected):
    problems = corpus.check(replace(md, old, new), log.events)
    assert any(expected in p for p in problems), problems
    assert all(p.startswith("line ") for p in problems)


def test_many_transcript_differences_are_counted(md, log):
    shifted = md.replace("· 00:", "· 02:")
    problems = corpus.check(shifted, log.events)
    assert len(problems) == 9 and all("should be" in p for p in problems)  # the blocks still follow their lines
    added = md + "".join(f"**D1** · 02:00:{s:02d} · Lisää.\n" for s in range(25))
    problems = corpus.check(added, log.events)
    assert problems[-1] == "… and 5 more transcript differences" and len(problems) == 21


@pytest.mark.parametrize("groups, expected", [
    ("[[A2, B1]]", None),
    ("[[A2, B1, C2], [A1, C1]]", None),
    ("[[A2, Z9]]", "same_speaker names Z9, which the transcript doesn't have"),
    ("[[A2]]", "the same_speaker group [A2] needs two labels or more"),
    ("A2", "same_speaker should be a list of groups, like [[A2, B1]]"),
])
def test_same_speaker_labels_must_exist(md, log, groups, expected):
    problems = corpus.check(md.replace("same_speaker: []", f"same_speaker: {groups}"), log.events)
    assert problems == ([] if expected is None else [f"line 3: {expected}"])


def test_done_needs_a_mark_on_every_candidate_and_repeat(md, log):
    done = md.replace("status: not started", "status: done")
    problems = corpus.check(done, log.events)
    assert [p.split(": ", 1)[1] for p in problems] == [
        "C1 has no mark, and the status is done", "C2 has no mark, and the status is done",
        "the repeat of C1 has no mark, and the status is done", "C3 has no mark, and the status is done",
        "C4 has no mark, and the status is done"]
    assert corpus.check(marked(done), log.events) == []
    assert corpus.check(marked(md).replace("status: not started", "status: in progress"), log.events) == []


MISSED = "```yaml carl-missed\nkind: claim\nshould_say: Sibelius completed seven symphonies.\n```\n"


@pytest.mark.parametrize("missed, expected", [
    (MISSED, None),
    (MISSED.replace("kind: claim", "kind: open question"), None),
    (MISSED.replace("kind: claim\n", ""), "a missed block's kind is claim or open question, not empty"),
    (MISSED.replace("kind: claim", "kind: fact"), "a missed block's kind is claim or open question, not fact"),
    (MISSED.replace("should_say: Sibelius completed seven symphonies.", "should_say:"),
     "a missed block needs should_say"),
])
def test_missed_blocks_need_a_kind_and_what_to_say(md, log, missed, expected):
    corrected = replace(md, "**C1** · 01:03:20 · Sibelius sävelsi kahdeksan sinfoniaa.\n",
                        "**C1** · 01:03:20 · Sibelius sävelsi kahdeksan sinfoniaa.\n\n" + missed + "\n")
    problems = corpus.check(corrected, log.events)
    assert problems == [] if expected is None else len(problems) == 1 and expected in problems[0]


def test_a_missed_block_goes_under_an_utterance(md, log):
    early = replace(md, "format: 1\n```\n", "format: 1\n```\n\n" + MISSED)
    assert any("goes under the utterance" in p for p in corpus.check(early, log.events))


@pytest.mark.parametrize("old, new, expected", [
    ("status: not started", "status: finished", "status finished isn't one of: not started, in progress, done"),
    ("format: 1", "format: 2", "format 2; this Carl reads format 1"),
    (f"session: {ID}", f"session: {OTHER}", f"session {OTHER} should be {ID}"),
])
def test_the_header_is_checked(md, log, old, new, expected):
    assert corpus.check(md.replace(old, new), log.events) == [f"line 3: {expected}"]


def test_the_files_blocks_must_be_readable(md, log):
    assert corpus.check(md.replace("```yaml carl-candidate\nrepeat_of", "```yaml carl-mised\nrepeat_of"),
                        log.events)[0].endswith("a block `carl-mised` Carl doesn't know "
                                                "(it knows carl-session, carl-candidate, carl-missed)")
    broken = md.replace("verdict: {A: wrong, B: wrong,", "verdict: {A: wrong, B: wrong")
    problems = corpus.check(broken, log.events)
    assert problems[0].startswith("line ") and "without a `,`" in problems[0]
    assert "C1 is missing" in problems[1]
    unclosed = md + "\n```yaml carl-missed\nkind: claim\n"
    assert corpus.check(unclosed, log.events)[0].endswith("the block `carl-missed` isn't closed")
    assert corpus.check("# Nothing here\n", log.events)[0] == "no `yaml carl-session` header"


def test_without_the_recording_the_file_is_checked_on_its_own(md):
    assert corpus.check(mark(md, "id: C3", "deserved"), None)[0].endswith("C3 has the mark deserved; a candidate "
                                                                          "with no card's mark is one of: ok, "
                                                                          "should show")
    assert corpus.check(replace(md, "**A2** · 00:04:31", "**A2** · 00:04:32"), None) == []
    assert corpus.check(md.replace("same_speaker: []", "same_speaker: [[A2, Z9]]"), None) == [
        "line 3: same_speaker names Z9, which the transcript doesn't have"]


def test_notes_can_run_over_several_lines(md, log):
    corrected = mark(marked(md), "id: C2", "|\n  Casablanca was settled at the table\n  a minute before.", "note")
    assert corpus.check(corrected, log.events) == []
    assert fields(corrected, "id: C2")["note"] == "Casablanca was settled at the table\na minute before."


def test_describe_and_status(md):
    assert corpus.describe(md) == "11 utterances, 4 candidates (2 shown), 1 repeat, status not started"
    done = marked(md).replace("status: not started", "status: done")
    assert corpus.describe(done) == "11 utterances, 4 candidates (2 shown), 1 repeat, 5 of 5 marked, 0 missed, " \
                                    "status done"
    assert corpus.status(done) == "done" and corpus.session_of(done) == ID


def test_started(md):
    assert corpus.started(md) is None
    assert corpus.started(md.replace("status: not started", "status: in progress")) == "its status is in progress"
    assert corpus.started(mark(md, "id: C1", "deserved")) == "its status is `not started`, but it has 1 mark"
    with_work = mark(mark(md, "id: C1", "x", "note"), "id: C2", "y", "note")
    assert corpus.started(with_work.replace("same_speaker: []", "same_speaker: [[A1, B1]]")) == \
        "its status is `not started`, but it has 2 notes, same_speaker groups"
    assert corpus.started(md + "\n```yaml carl-missed\n").startswith("it can't be read")


# --- The YAML subset ---------------------------------------------------------------------------


@pytest.mark.parametrize("value", [
    "plain", "not started", "plain:agreed", "https://x.org/a_(b)?c=d&e=%C3%A4", "Kallio, Helsinki",
    "Bogart's \"Rick\"", "a: b", "x #y", "C#", "1952", "0.5", "true", "null", "~", "", " lead", "trail ",
    "ääkköset ja ÅÄÖ", "line\nbreak", "[not a list]", "{x}", "- dash", "it's", "'quoted'", "Probably: yes.",
    Text("prose"), 3, 0.93, 1e-05, -2, True, False, None, [], {}, ["a b", "c,d", None, 1, ["x", "y"]],
    {"A": "not found", "B": "it's: tricky", "same_fact": 0.93, "supported": [None, 0.71]},
])
def test_values_read_back_as_written(value):
    assert corpus.value(corpus.dump(value)) == value
    assert corpus.load([f"key: {corpus.dump(value)}   # a comment"]) == {"key": value}
    assert corpus.value(corpus.dump([value, value])) == [value, value]


def test_bare_and_quoted_strings():
    assert corpus.dump("not started") == "not started"
    assert corpus.dump(Text("not started")) == '"not started"'
    assert corpus.dump(["Kallio, Helsinki"]) == '["Kallio, Helsinki"]'
    assert corpus.dump({"A": "not found", "B": "1952"}) == '{A: not found, B: "1952"}'


def test_the_subset_reads_what_an_owner_writes():
    text = """\
# a comment line
id: C1
mark: already settled      # with a comment
note: 'it''s # not a comment'
card: "Rick Blaine \\u2013 Bogart"
long: this note goes
  on over two lines
folded: >
  one
  two

  three
kept: |-
  first
    indented
restated: {A: "x, y", B: 'z'}
under:     # a mapping in lines under its key
  A: >
    one: # two

  # a comment
  B: [x, y]
  C:
    deeper: 1
empty:
"""
    assert corpus.load(text.splitlines()) == {
        "id": "C1", "mark": "already settled", "note": "it's # not a comment", "card": "Rick Blaine – Bogart",
        "long": "this note goes on over two lines", "folded": "one two\nthree", "kept": "first\n  indented",
        "restated": {"A": "x, y", "B": "z"}, "under": {"A": "one: # two", "B": ["x", "y"], "C": {"deeper": 1}},
        "empty": None,
    }


def test_folded_prose_is_wrapped_to_fit_88_columns():
    a = ("Suomessa informaatioympäristön vuoksi tavalliset ihmiset eivät saa mielipiteitään julki valtalehdissä "
         "tai suurilla televisiokanavilla, ja rasistisiksi, fasistisiksi, äärioikeistolaisiksi, konservatiivisiksi "
         "tai perussuomalaisiksi tulkitut mielipiteet estävät yliopistotyön tai Yleisradiossa toimimisen.")
    b = "Konservatiivisten tai perussuomalaisten mielipiteiden esittäjä ei voi saada työpaikkaa yliopistosta."
    written = corpus.yaml_lines([("restated", {"A": Folded(a), "B": Folded(b)}), ("mark", None, "ok")])
    assert written == [
        "restated:",
        "  A: >",
        "    Suomessa informaatioympäristön vuoksi tavalliset ihmiset eivät saa mielipiteitään",
        "    julki valtalehdissä tai suurilla televisiokanavilla, ja rasistisiksi, fasistisiksi,",
        "    äärioikeistolaisiksi, konservatiivisiksi tai perussuomalaisiksi tulkitut mielipiteet",
        "    estävät yliopistotyön tai Yleisradiossa toimimisen.",
        "  B: >",
        "    Konservatiivisten tai perussuomalaisten mielipiteiden esittäjä ei voi saada",
        "    työpaikkaa yliopistosta.",
        "mark:                   # ok",
    ]
    assert max(map(len, written)) <= corpus.WIDTH
    assert corpus.load(written) == {"restated": {"A": a, "B": b}, "mark": None}


@pytest.mark.parametrize("prose", ["C# on # kieli: kyllä", "- dash", "> quote", "\"quoted\"", "x" * 100,
                                   "https://fi.wikipedia.org/wiki/" + "a" * 90 + " ja muuta"])
def test_folded_prose_reads_back_as_written(prose):
    written = corpus.yaml_lines([("restated", {"A": Folded(prose)})])
    assert corpus.load(written) == {"restated": {"A": prose}}
    assert corpus.value(corpus.dump([Folded(prose)])) == [prose]  # in quotes on one line


def test_a_restatement_that_isnt_text_is_written_as_it_is():
    assert corpus.yaml_lines([("restated", {"A": Folded("Kuu on juustoa."), "B": 3})]) == [
        "restated:", "  A: >", "    Kuu on juustoa.", "  B: 3"]


@pytest.mark.parametrize("text, expected", [
    ("mark: a\nmark: b", "line 2: `mark` a second time"),
    ("mark:deserved", "line 1: not a `key: value` line"),
    ("  mark: a", "line 1: an indented line"),
    ("verdict: [a, b", "line 1: a list without its `]`"),
    ("verdict: {a: 1", "line 1: a mapping without its `}`"),
    ('card: "open', "line 1: a string without its closing"),
    ("card: 'open", "line 1: a string without its closing"),
    ('card: "a" b', "line 1: unexpected"),
    ('card: "bad \\q escape"', "line 1: a string that can't be read"),
    ("v: {a b}", "line 1: a key 'a b' without a `:`"),
    ("restated:\n    A: >\n      x\n  B: y", "line 4: indented less than the `key:` lines above it"),
    ("restated:\n  A: x\n  A: y", "line 3: `A` a second time"),
    ("restated:\n\n  A: [x", "line 3: a list without its `]`"),
])
def test_the_subset_rejects_what_it_cant_read(text, expected):
    with pytest.raises(corpus.YamlError) as e:
        corpus.load(text.splitlines())
    assert str(e.value).startswith(expected)


# --- The owner's commands ------------------------------------------------------------------------


def jsonl(events: list) -> bytes:
    return b"".join(json.dumps(e, ensure_ascii=False).encode() + b"\n" for e in events)


@pytest.fixture
def store(log) -> MemoryStore:
    """The dinner's recording, its log in three parts, and another recording."""
    store = MemoryStore()
    events = [e for e in log.events if isinstance(e, dict)]
    third = len(events) // 3
    for n, part in enumerate((events[:third], events[third:2 * third], events[2 * third:]), 1):
        store.objects[f"recordings/{ID}/events/{n:06d}.jsonl"] = jsonl(part)
    store.objects[f"recordings/{ID}/audio/000001.pcm"] = b"\0" * 3200
    other = Log(OTHER).start()
    other.open(0.5, 1)
    other.say(3, 1, "1", "Hei.")
    other.end(10, 9.0, 0.0003)
    store.objects[f"recordings/{OTHER}/events/000001.jsonl"] = jsonl(other.events)
    return store


def corpus_file(store: MemoryStore, session_id: str = ID) -> str:
    return store.objects[f"corpus/{session_id}.md"].decode()


async def test_generate_writes_the_corpus_file(store, md, capsys):
    assert await owner.generate(store, ID) == 0
    assert corpus_file(store) == md
    assert capsys.readouterr().out == f"Wrote corpus/{ID}.md: 11 utterances, 4 candidates (2 shown), 1 repeat, " \
                                      "status not started.\n"
    assert await owner.generate(store, ID) == 0  # a draft not started is written again
    assert capsys.readouterr().out.startswith(f"Rewrote corpus/{ID}.md")


@pytest.mark.parametrize("change", [
    lambda md: md.replace("status: not started", "status: in progress"),
    lambda md: md.replace("status: not started", "status: done"),
    lambda md: mark(md, "id: C1", "deserved"),
    lambda md: md.replace("same_speaker: []", "same_speaker: [[A1, B1]]"),
    lambda md: md + "\n```yaml carl-missed\nkind: claim\nshould_say: x\n```\n",
    lambda md: md.replace("```yaml carl-session", "```yaml carl-session\nbroken"),
])
async def test_generate_never_overwrites_a_started_correction(store, md, change):
    started = change(md)
    store.objects[f"corpus/{ID}.md"] = started.encode()
    with pytest.raises(Kept, match=f"corpus/{ID}.md is kept as it is: it"):
        await owner.generate(store, ID)
    assert corpus_file(store) == started


async def test_generate_after_a_stopped_recording_refuses_cleanly(store):
    await store.delete_prefix(f"recordings/{ID}/")
    with pytest.raises(OwnerError, match="no event log to generate from: its recording was stopped and deleted"):
        await owner.generate(store, ID)
    assert f"corpus/{ID}.md" not in store.objects
    with pytest.raises(OwnerError, match="not a session id"):
        await owner.generate(store, "20260927T160000Z-a1b2c")


async def test_generate_all_keeps_started_files(store, md, capsys):
    store.objects[f"corpus/{ID}.md"] = md.replace("status: not started", "status: in progress").encode()
    assert await owner.generate_all(store) == 0
    out = capsys.readouterr().out
    assert f"Wrote corpus/{OTHER}.md: 1 utterance" in out
    assert f"corpus/{ID}.md is kept as it is: its status is in progress." in out
    store.objects[f"recordings/{OTHER}/events/000001.jsonl"] = b'{"event": "utterance"}\n'
    assert await owner.generate_all(store) == 1
    assert "no `session start` event" in capsys.readouterr().out


async def test_fetch_downloads_the_file_and_never_overwrites_local_edits(store, tmp_path, capsys):
    with pytest.raises(OwnerError, match=f"there is no corpus/{ID}.md: make it with `carl owner generate {ID}`"):
        await owner.fetch_corpus(store, ID, tmp_path)
    await owner.generate(store, ID)
    assert await owner.fetch_corpus(store, ID, tmp_path) == 0
    local = tmp_path / f"{ID}.md"
    assert local.read_text() == corpus_file(store)
    assert f"corpus/{ID}.md → {local}" in capsys.readouterr().out
    assert await owner.fetch_corpus(store, ID, tmp_path) == 0
    assert "already the same" in capsys.readouterr().out
    local.write_text(mark(local.read_text(), "id: C1", "deserved"))
    with pytest.raises(OwnerError, match="exists and differs"):
        await owner.fetch_corpus(store, ID, local)
    assert "mark: deserved" in local.read_text()
    assert await owner.fetch_corpus(store, ID, tmp_path / "new" / "folder") == 0
    assert await owner.fetch_corpus(store, ID, tmp_path / "new" / "named.md") == 0
    assert sorted(p.name for p in (tmp_path / "new").rglob("*.md")) == [f"{ID}.md", "named.md"]


async def test_fetch_goes_to_the_carl_corpus_folder_by_default(store, tmp_path, monkeypatch):
    monkeypatch.setattr(owner, "CORPUS", tmp_path / "carl-corpus")
    await owner.generate(store, ID)
    await owner.fetch_corpus(store, ID, None)
    assert (tmp_path / "carl-corpus" / f"{ID}.md").is_file()


async def test_check_and_put(store, md, tmp_path, capsys):
    await owner.generate(store, ID)
    capsys.readouterr()
    local = tmp_path / "dinner.md"
    local.write_text(mark(replace(md, "id: C2", "id: C9"), "id: C1", "great"))
    with pytest.raises(OwnerError, match="doesn't pass the check"):
        await owner.check_corpus(store, local)
    out = capsys.readouterr().out
    assert out.startswith(f"{local} has 3 problems:\n  line ") and "C2 is missing" in out
    with pytest.raises(OwnerError, match="doesn't pass the check"):
        await owner.put_corpus(store, local)
    assert corpus_file(store) == md  # nothing uploaded

    corrected = marked(md).replace("status: not started", "status: done")
    local.write_text(corrected)
    assert await owner.check_corpus(store, local) == 0
    assert "passes the check: 11 utterances, 4 candidates (2 shown), 1 repeat, 5 of 5 marked" in \
        capsys.readouterr().out
    assert await owner.put_corpus(store, local) == 0
    assert corpus_file(store) == corrected
    assert f"{local} → corpus/{ID}.md" in capsys.readouterr().out
    with pytest.raises(Kept):
        await owner.generate(store, ID)


async def test_put_reminds_of_a_status_left_not_started(store, md, tmp_path, capsys):
    local = tmp_path / "dinner.md"
    local.write_text(mark(md, "id: C1", "deserved"))
    await owner.put_corpus(store, local)
    assert "Its status is still `not started`" in capsys.readouterr().out


async def test_put_after_the_recording_expired_checks_the_file_alone(store, md, tmp_path, capsys):
    await store.delete_prefix(f"recordings/{ID}/")
    local = tmp_path / "dinner.md"
    local.write_text(marked(md))
    assert await owner.put_corpus(store, local) == 0
    assert "is gone, so" in capsys.readouterr().out
    assert corpus_file(store) == marked(md)


@pytest.mark.parametrize("content, expected", [
    ("# no header\n", "no `yaml carl-session` header with the session id"),
    ("```yaml carl-session\nsession: ../x\n```\n", "not a session id"),
])
async def test_put_needs_the_session_id_in_the_header(store, tmp_path, content, expected):
    local = tmp_path / "x.md"
    local.write_text(content)
    with pytest.raises(OwnerError, match=expected):
        await owner.put_corpus(store, local)
    with pytest.raises(OwnerError, match="can't read"):
        await owner.check_corpus(store, tmp_path / "missing.md")


MONTH = {"month": "2026-09", "usd": 1.5, "estimated_usd": 0.0023, "charges": 214, "updated": "2026-09-27T16:10:00Z",
         "by_stage": {"speech-to-text": 0.9, "decision": 0.1, "fact-finding A": 0.3, "fact-finding B": 0.15,
                      "fact-checking": 0.05},
         "by_provider": {"soniox": 0.9, "openai": 0.4, "perplexity": 0.15, "openrouter": 0.05}}


async def test_month_prints_the_totals_per_provider_and_stage(capsys):
    store = MemoryStore()
    store.objects["costs/month-2026-09.json"] = json.dumps(MONTH).encode()
    assert await owner.month_totals(store, "2026-09") == 0
    assert capsys.readouterr().out == """\
2026-09 in Helsinki time: 214 charges, the last at 2026-09-27 19:10 Helsinki time. USD, as billed.

provider       USD
soniox      0.9000
openai      0.4000
perplexity  0.1500
openrouter  0.0500
total       1.5000

stage              USD
speech-to-text  0.9000
fact-finding A  0.3000
fact-finding B  0.1500
decision        0.1000
fact-checking   0.0500
total           1.5000

Of the total, 0.0023 USD is estimated: calls whose usage wasn't known.
"""


async def test_month_without_costs_or_with_a_bad_month(capsys):
    store = MemoryStore()
    assert await owner.month_totals(store, "2026-08") == 0
    assert capsys.readouterr().out == "No costs for 2026-08.\n"
    assert await owner.month_totals(store, None) == 0
    assert capsys.readouterr().out.startswith("No costs for 20")
    with pytest.raises(OwnerError, match="not a month"):
        await owner.month_totals(store, "2026-13")
    for bad in (b"{", b'{"usd": 1}', b'{"usd": 1, "charges": 2, "by_stage": {"decision": "?"}}'):
        store.objects["costs/month-2026-07.json"] = bad
        with pytest.raises(OwnerError, match="can't be read"):
            await owner.month_totals(store, "2026-07")


def test_the_cli_runs_the_corpus_commands(store, tmp_path, monkeypatch, capsys):
    devs = []
    monkeypatch.setattr(owner, "open_store", lambda dev: devs.append(dev) or store)
    store.objects["costs/month-2026-09.json"] = json.dumps(MONTH).encode()
    assert cli.main(["owner", "generate", ID, "--dev"]) == 0
    assert cli.main(["owner", "generate", "--all"]) == 0
    assert cli.main(["owner", "generate"]) == 1
    assert "give a session id or --all" in capsys.readouterr().err
    assert cli.main(["owner", "fetch", ID, "--out", str(tmp_path)]) == 0
    local = tmp_path / f"{ID}.md"
    local.write_text(marked(local.read_text()))
    assert cli.main(["owner", "check", str(local)]) == 0
    assert cli.main(["owner", "put", str(local), "--dev"]) == 0
    assert "mark: deserved" in corpus_file(store)
    assert cli.main(["owner", "month", "2026-09"]) == 0
    assert "soniox" in capsys.readouterr().out
    local.write_text(mark(local.read_text(), "id: C1", "great"))
    assert cli.main(["owner", "put", str(local)]) == 1
    assert "doesn't pass the check" in capsys.readouterr().err
    assert devs == [True, False, False, False, False, True, False, False]


# --- Against what the server really records ------------------------------------------------------


async def test_a_recording_sessions_own_log(unlocked, stt, store):
    """A session through the server, with the scripted speech-to-text."""
    from .test_session import connect, receive, settle, start

    ws = await connect(unlocked)
    session_id = (await start(ws))["session"]
    await settle()
    stt.streams[0].say("1", "Helsinki perustettiin vuonna 1550.", start_ms=1000)
    stt.streams[0].say("2", "Niin olikin.", start_ms=4000)
    await settle()
    await ws.send_json({"type": "pause"})
    await receive(ws, "session")
    await ws.send_json({"type": "resume"})
    await receive(ws, "session")
    await settle()
    stt.streams[1].say("1", "Jatketaan.", start_ms=500)
    await settle()
    await ws.send_json({"type": "end"})
    await receive(ws, "ended")
    events = await owner.read_events(store, session_id)
    md = corpus.generate(events)
    said = [line for line in lines(md) if line.startswith("**")]
    assert [line.split(" · ")[0] for line in said] == ["**A1**", "**A2**", "**B1**"]
    assert said[0].endswith(" · 00:00:01 · Helsinki perustettiin vuonna 1550. \\")
    assert said[1].split(" · ")[1] == "00:00:04"
    assert any(line.startswith("*— paused 00:00:0") for line in lines(md))
    header = fields(md, f"session: {session_id}")
    assert header["config"].startswith("config.toml@") and header["status"] == "not started"
    assert corpus.check(md, events) == []


async def test_a_checked_candidates_own_events():
    """A candidate checked by the real Checker, with fake fact-finders and fact-checking model."""
    import asyncio

    from carl.checking import PageMatch
    from carl.checks import Checker
    from carl.config import load_config
    from carl.prompts import load_prompts
    from carl.session import Session, Sessions

    from .conftest import ROOT
    from .test_checks import EN_CARD, SUPPORTED, FakeFinder, FakeLink, FakeTyped, flag, reply, say
    from .test_decision import Events

    sessions = Sessions(load_config(ROOT / "config.toml"), load_prompts(ROOT / "prompts"), MemoryStore(), None, "t")
    session = Session(sessions, ID, record=True, timezone="Europe/Helsinki")
    session.recorder, session.link = Events(), FakeLink()
    candidate = flag(session, say(session, "Who played Rick in Casablanca?", language="en"), "open question")

    async def download(self, session, candidate, finder, draft):
        page = PageMatch(True, match="normalised")
        session.log("download", candidate=candidate.id, finder=finder, url=draft.source_url, cost_usd=0.0,
                    **page.event())
        return page

    checker = Checker(sessions, {"A": FakeFinder(reply("question answered", EN_CARD), letter="A"),
                                 "B": FakeFinder(reply("question answered", EN_CARD, restatement="Rick?"))},
                      FakeTyped(SUPPORTED, SUPPORTED, ("same fact", {"same fact": 0.9, "contradict": 0.1})))
    checker.download = download.__get__(checker)
    checker.start(session, candidate)
    while session.checks:
        await asyncio.wait(set(session.checks))
    session.card_reported("shown", candidate.id, at(10))
    events = [{"time": at(0), "event": "session start", "session": ID},
              {"time": at(0), "event": "utterance", **candidate.heard.event()},
              {"time": at(1), "event": "candidate", **candidate.event()}, *session.recorder.events]
    c1 = fields(corpus.generate(events), "id: C1")
    assert c1["shown"] == "plain" and c1["late"] is False and c1["title"] == EN_CARD.title
    assert c1["card"] == EN_CARD.fact and c1["source"] == EN_CARD.source_url
    assert c1["restated"] == {"A": "Helsingin olympialaiset olivat vuonna 1956.", "B": "Rick?"}
    assert c1["verdict"] == {"A": "answered", "B": "answered", "same_fact": 0.9, "supported": [0.93, 0.93],
                             "verified": ["page", "snippet"], "reason": "plain:agreed"}
