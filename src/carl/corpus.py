"""The test corpus Markdown (spec section 9, The test corpus Markdown and
Correcting it): `corpus/<id>.md`, made from a recording session's event log
and corrected by the owner.

`generate(events)` is a pure function of the event log: every event of
`recordings/<id>/events/*.jsonl`, in order. The file it writes has

1. a `yaml carl-session` header: the session id; the place or places in
   order, as neighbourhood and town (never coordinates); the listening time
   (paused time excluded); the config file and its hash; the session's cost;
   the correction `status` (`not started`); the owner's `same_speaker`
   groups (`[]`); and the format version;
2. the transcript, one line per utterance, `**A2** · 00:04:31 · text`, with
   the time counted from Start to its first word. Small talk and skipped
   backchannel are there too, and `paused` and `gap` markers sit where Carl
   heard nothing. The speaker labels are the decision call's: stream 1's
   speaker 2 is A2, stream 2's is B2. A line followed by another ends in
   ` \\`, Markdown's hard line break, so a run of lines shows one per line;
3. a `yaml carl-candidate` block right after each candidate's utterance:
   Carl's id, the kind, whether and how it was shown, late, the check time,
   the card (a `>` block when in quotes it would pass column 88), both
   restatements (each a `>` block, to fit 88 columns) and the verdict
   summary with the band's reason code. A repeat's block holds `repeat_of`
   and its probability. Every block ends with the owner's `mark` and
   `note`, left empty.

The owner adds a `yaml carl-missed` block (`kind`, `should_say`) under each
utterance Carl should have caught. `check(markdown, events)` lists what is
wrong with a corrected file.

Events the generator doesn't know are skipped, and a candidate's block holds
only what its events say, so a recording made before a stage existed has
fewer blocks: a step-2 recording has only the transcript.

**The YAML subset.** There is no YAML library, so the blocks are written and
read in a small subset of YAML 1.2, which any YAML parser reads the same way:

- one `key: value` per line, the key a bare word; `#` after a space, or at
  the start of a line, begins a comment;
- a value is empty or `null` (nothing), `true`/`false`, a number, a string,
  a flow list `[a, b]` or a flow mapping `{a: 1, b: 2}`, nested as needed;
- a string is bare (plain) or in double quotes with JSON's escapes; single
  quotes (`'it''s'`) are read too. A bare string in a list or mapping can't
  hold `,[]{}`. Quote any string that holds `: ` or ` #`, or that would read
  as a number, `true`, `false` or `null`;
- a long value may go on in lines indented under it, joined with spaces, and
  `|` or `>` starts a block of indented lines (a note of several lines), read
  without its last line break;
- a key with nothing after it may have `key: value` lines indented under it
  instead, a mapping (`restated`, its `A: >` and `B: >` blocks).
"""

from __future__ import annotations

import difflib
import hashlib
import json
import re
import textwrap
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .decision import stream_letters

FORMAT = 1
CONFIG_FILE = "config.toml"
STATUSES = ("not started", "in progress", "done")
# The owner's marks: for a shown card, for a candidate that got no card, and for a repeat.
MARKS = {
    "shown": ("deserved", "wrong", "nitpick", "opinion", "contested", "already settled", "not checkable"),
    "silent": ("ok", "should show"),
    "repeat": ("ok", "bad match"),
}
MISSED_KINDS = ("claim", "open question")
BLOCKS = ("carl-session", "carl-candidate", "carl-missed")
FINDERS = ("A", "B")
OUTCOMES = {"claim is wrong": "wrong", "claim is right": "right", "question answered": "answered",
            "not found": "not found"}
CARD_EVENTS = ("card sent", "card shown", "card filed", "card withdrawn")
UNKNOWN_CANDIDATE = "unknown"  # a repeat whose candidate the decision call couldn't name
DEFAULT_ZONE = "Europe/Helsinki"
COMMENT_AT = 24  # the column a comment starts at, where the line leaves room
WIDTH = 88  # the column a `>` block's lines are wrapped at
INDENT = "  "  # what each line under a key is indented by
MOST_DIFFERENCES = 20  # transcript differences listed before the rest are counted


class CorpusError(Exception):
    """The event log can't make a corpus file."""


# --- The YAML subset -----------------------------------------------------------------------


class YamlError(ValueError):
    pass


class Text(str):
    """Prose, such as a card's text: always written in quotes, to read as one piece."""


class Folded(Text):
    """Prose `yaml_lines` writes as a `>` block wrapped at WIDTH columns, a
    mapping that holds it going in lines under its key. In a list or mapping
    on one line, it is in quotes as Text is."""


class Wrapped(Folded):
    """Prose in quotes on its key's line when that fits WIDTH columns, else Folded."""


_NUMBER = re.compile(r"[-+]?(\d+(\.\d*)?|\.\d+)([eE][-+]?\d+)?")
_INTEGER = re.compile(r"[-+]?\d+")
_KEY = re.compile(r"([A-Za-z_][\w-]*)[ \t]*:(?:[ \t]+(.*))?")
_BLOCK_SCALAR = re.compile(r"[|>][-+]?")


def scalar(text: str) -> Any:
    """A bare scalar's value: None, a bool, a number or the string itself."""
    if text in ("", "~", "null", "Null", "NULL"):
        return None
    if text in ("true", "True", "TRUE", "false", "False", "FALSE"):
        return text.lower() == "true"
    if _NUMBER.fullmatch(text):
        return int(text) if _INTEGER.fullmatch(text) else float(text)
    return text


def _bare(text: str, flow: bool) -> bool:
    """Whether a string can be written bare and read back as the same string."""
    return (bool(text) and text[0].isalnum() and text == text.strip() and not text.endswith(":")
            and ": " not in text and " #" not in text and not any(c in text for c in "\"\n\r\t")
            and not (flow and any(c in text for c in ",[]{}")) and scalar(text) == text)


def dump(value: Any, flow: bool = False) -> str:
    """A value in the subset. None is empty at the top level and `null` inside a list or mapping."""
    if value is None:
        return "null" if flow else ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return json.dumps(value)
    if isinstance(value, Mapping):
        return "{" + ", ".join(f"{dump(str(k), True)}: {dump(v, True)}" for k, v in value.items()) + "}"
    if isinstance(value, list | tuple):
        return "[" + ", ".join(dump(v, True) for v in value) + "]"
    text = str(value)
    return text if _bare(text, flow) and not isinstance(value, Text) else json.dumps(text, ensure_ascii=False)


def uncomment(text: str) -> str:
    """The text before a comment: a `#` at the start or after a space, outside quotes."""
    quote, i = None, 0
    while i < len(text):
        c = text[i]
        if quote == '"':
            if c == "\\":
                i += 1
            elif c == '"':
                quote = None
        elif quote == "'":
            if text[i:i + 2] == "''":
                i += 1
            elif c == "'":
                quote = None
        elif c in "\"'" and (i == 0 or text[i - 1] in " \t[{,:"):
            quote = c
        elif c == "#" and (i == 0 or text[i - 1] in " \t"):
            return text[:i]
        i += 1
    return text


class _Flow:
    """Reads one value: a quoted string, or a flow list or mapping."""

    def __init__(self, text: str) -> None:
        self.text, self.pos = text, 0

    def fail(self, what: str) -> YamlError:
        return YamlError(f"{what} in {self.text!r}")

    def peek(self) -> str:
        while self.pos < len(self.text) and self.text[self.pos] in " \t":
            self.pos += 1
        return self.text[self.pos] if self.pos < len(self.text) else ""

    def done(self) -> None:
        if self.peek():
            raise self.fail(f"unexpected {self.text[self.pos:]!r}")

    def value(self, stops: str = "") -> Any:
        c = self.peek()
        if c == "[":
            return self.sequence()
        if c == "{":
            return self.mapping()
        if c == '"':
            return self.double()
        if c == "'":
            return self.single()
        start = self.pos
        while self.pos < len(self.text) and self.text[self.pos] not in stops and not self.key_ends():
            self.pos += 1
        return scalar(self.text[start:self.pos].strip())

    def key_ends(self) -> bool:
        """At a `: `, which ends a bare key and can't be part of a bare value in a list or mapping."""
        return self.text[self.pos] == ":" and self.text[self.pos + 1:self.pos + 2] in ("", " ", "\t")

    def sequence(self) -> list[Any]:
        self.pos += 1
        items: list[Any] = []
        while (c := self.peek()) != "]":
            if not c:
                raise self.fail("a list without its `]`")
            items.append(self.value(",]}"))
            if (c := self.peek()) == ",":
                self.pos += 1
            elif not c:
                raise self.fail("a list without its `]`")
            elif c != "]":
                raise self.fail("a list item without a `,` after it")
        self.pos += 1
        return items

    def mapping(self) -> dict[str, Any]:
        self.pos += 1
        items: dict[str, Any] = {}
        while (c := self.peek()) != "}":
            if not c:
                raise self.fail("a mapping without its `}`")
            key = self.value(":,}") if c in "\"'" else scalar(self.bare_key())
            if self.peek() != ":":
                raise self.fail(f"a key {key!r} without a `:` after it")
            self.pos += 1
            items[str(key)] = None if self.peek() in ",}" else self.value(",]}")
            if (c := self.peek()) == ",":
                self.pos += 1
            elif not c:
                raise self.fail("a mapping without its `}`")
            elif c != "}":
                raise self.fail("a mapping item without a `,` after it")
        self.pos += 1
        return items

    def bare_key(self) -> str:
        start = self.pos
        while self.pos < len(self.text) and self.text[self.pos] not in ":,}":
            self.pos += 1
        return self.text[start:self.pos].strip()

    def double(self) -> str:
        end = self.pos + 1
        while end < len(self.text) and self.text[end] != '"':
            end += 2 if self.text[end] == "\\" else 1
        if end >= len(self.text):
            raise self.fail("a string without its closing `\"`")
        try:
            text = json.loads(self.text[self.pos:end + 1])
        except ValueError as e:
            raise self.fail(f"a string that can't be read ({e.args[0]})") from None
        self.pos = end + 1
        return text

    def single(self) -> str:
        end = self.pos + 1
        while True:
            end = self.text.find("'", end)
            if end < 0:
                raise self.fail("a string without its closing `'`")
            if self.text[end + 1:end + 2] != "'":
                break
            end += 2
        text = self.text[self.pos + 1:end].replace("''", "'")
        self.pos = end + 1
        return text


def value(text: str) -> Any:
    """A top-level value, its comment already gone. A bare string there may hold `,[]{}`."""
    text = text.strip()
    if not text or text[0] not in "[{\"'":
        return scalar(text)
    flow = _Flow(text)
    result = flow.value()
    flow.done()
    return result


def load(lines: Sequence[str], first: int = 1) -> dict[str, Any]:
    """A block's `key: value` lines as a dict. `first` is the first line's
    number in the file, for the errors (YamlError)."""
    data: dict[str, Any] = {}
    i = 0
    while i < len(lines):
        line = lines[i]
        where = f"line {first + i}"
        if not line.strip() or line.lstrip().startswith("#"):
            i += 1
            continue
        if line[0] in " \t":
            raise YamlError(f"{where}: an indented line with no `key:` above it")
        m = _KEY.fullmatch(line.rstrip())
        if m is None:
            raise YamlError(f"{where}: not a `key: value` line: {line.strip()!r}")
        key, text = m[1], uncomment(m[2] or "").strip()
        if key in data:
            raise YamlError(f"{where}: `{key}` a second time")
        i += 1
        start = i
        more = []
        while i < len(lines) and (not lines[i].strip() or lines[i][0] in " \t"):
            more.append(lines[i])
            i += 1
        while more and not more[-1].strip():  # blank lines after the value aren't part of it
            more.pop()
        if not text and (mapping := _mapping(more, first + start)) is not None:
            data[key] = load(mapping, first + start)
            continue
        try:
            if _BLOCK_SCALAR.fullmatch(text):
                data[key] = _block_scalar(text[0], more)
            else:
                data[key] = value(" ".join(p for p in [text, *(uncomment(s).strip() for s in more)] if p))
        except YamlError as e:
            raise YamlError(f"{where}: {e}") from None
    return data


def _mapping(lines: list[str], first: int) -> list[str] | None:
    """The lines under a key with nothing after it, dedented, when they are a
    mapping: the first of them, comments aside, is a `key:` line."""
    head = next((s for s in lines if s.strip() and not s.lstrip().startswith("#")), None)
    if head is None or not _KEY.fullmatch(head.strip()):
        return None
    indent = len(head) - len(head.lstrip())
    dedented = []
    for n, line in enumerate(lines):
        text = line.lstrip()
        if len(line) - len(text) >= indent:
            dedented.append(line[indent:])
        elif not text or text.startswith("#"):
            dedented.append(text)
        else:
            raise YamlError(f"line {first + n}: indented less than the `key:` lines above it")
    return dedented


def _block_scalar(style: str, lines: list[str]) -> str:
    """`|` keeps the lines, `>` folds them into one, a blank line being a line break."""
    indent = min((len(s) - len(s.lstrip()) for s in lines if s.strip()), default=0)
    lines = [s[indent:].rstrip() for s in lines]
    if style == "|":
        return "\n".join(lines).strip("\n")
    return "\n".join(" ".join(part.split("\n")) for part in "\n".join(lines).split("\n\n")).strip()


def yaml_lines(fields: Sequence[tuple[str, Any] | tuple[str, Any, str]], indent: str = "") -> list[str]:
    """A block's lines: `key: value`, with a comment where one is given.
    Folded prose goes in a `>` block (Wrapped prose when in quotes it would
    pass WIDTH columns), and a mapping holding it in lines under its key."""
    lines = []
    for key, content, *comment in fields:
        text, under = f"{indent}{key}: {dump(content)}".rstrip(), []
        folds = isinstance(content, Folded) and not (isinstance(content, Wrapped) and len(text) <= WIDTH)
        if folds and content.split():
            text = f"{indent}{key}: >"
            under = textwrap.wrap(" ".join(content.split()), WIDTH, initial_indent=indent + INDENT,
                                  subsequent_indent=indent + INDENT, break_long_words=False, break_on_hyphens=False)
        elif isinstance(content, Mapping) and any(isinstance(v, Folded) for v in content.values()):
            text = f"{indent}{key}:"
            under = yaml_lines([(str(k), v) for k, v in content.items()], indent + INDENT)
        if comment:
            text = f"{text.ljust(COMMENT_AT - 1)} # {comment[0]}"
        lines += [text, *under]
    return lines


# --- Reading the event log ----------------------------------------------------------------


def _time(event: Mapping[str, Any]) -> datetime | None:
    """The event's time; a time without its zone is UTC, as the recorder writes it."""
    try:
        t = datetime.fromisoformat(str(event["time"]).replace("Z", "+00:00"))
    except (KeyError, ValueError):
        return None
    return t if t.tzinfo is not None else t.replace(tzinfo=UTC)


def _number(value: Any) -> float | None:
    return float(value) if isinstance(value, int | float) and not isinstance(value, bool) else None


def clock(seconds: float) -> str:
    """Seconds from Start as `hh:mm:ss`, rounded down."""
    s = max(0, int(seconds))
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


def duration(seconds: float) -> str:
    """`1h46m`, or `35m12s` below an hour."""
    s = max(0, round(seconds))
    return f"{s // 3600}h{s % 3600 // 60:02d}m" if s >= 3600 else f"{s // 60}m{s % 60:02d}s"


def label(stream: Any, speaker: Any) -> str:
    """The speaker label as the decision call shows it: stream 1's speaker 2 is A2."""
    letters = stream_letters(stream) if isinstance(stream, int) and not isinstance(stream, bool) else ""
    return f"{letters}{'' if speaker is None else speaker}"


@dataclass
class Line:
    """An utterance's transcript line."""

    utterance: str  # Carl's id, U12
    label: str
    at: float  # seconds from Start to its first word
    text: str

    def ref(self) -> str:
        return f"{self.label} · {clock(self.at)}"


@dataclass
class Marker:
    """A stretch Carl didn't hear: `paused`, or a `gap` (speech-to-text or the page's connection down)."""

    kind: str
    start: float
    end: float | None  # None when the log stops first

    def text(self) -> str:
        span = f"{clock(self.start)}–{clock(self.end)}" if self.end is not None else f"from {clock(self.start)}"
        return f"*— {self.kind} {span} —*"


class _Clocks:
    """When each stream's words were said, in seconds from Start.

    Speech-to-text times words by the audio its stream got: wall time from
    the stream's opening, except that while the page's connection is down the
    stream stays open and gets no audio, so from the page's return its clock
    is behind by the time away (less the silence sent to finalise). Each
    stream keeps its stretches as (audio seconds, seconds from Start) at
    their starts.
    """

    def __init__(self) -> None:
        self.stretches: dict[Any, list[tuple[float, float]]] = {}
        self.away: dict[Any, float] = {}  # a stream's audio seconds when its page went, silence added

    def open(self, stream: Any, at: float) -> None:
        self.stretches[stream] = [(0.0, at)]
        self.away.pop(stream, None)

    def audio_at(self, stream: Any, at: float) -> float:
        audio, since = self.stretches[stream][-1]
        return audio + max(0.0, at - since)

    def page_gone(self, stream: Any, at: float) -> None:
        if stream in self.stretches and stream not in self.away:
            self.away[stream] = self.audio_at(stream, at)

    def silence(self, stream: Any, ms: Any) -> None:
        if stream in self.away and (s := _number(ms)) is not None:
            self.away[stream] += s / 1000

    def page_back(self, at: float) -> None:
        for stream, audio in self.away.items():
            self.stretches[stream].append((audio, at))
        self.away.clear()

    def said(self, stream: Any, audio_s: float) -> float | None:
        stretches = self.stretches.get(stream)
        if not stretches:
            return None
        audio, since = next((s for s in reversed(stretches) if s[0] <= audio_s), stretches[0])
        return since + audio_s - audio


@dataclass
class _Log:
    """What the generator takes from an event log."""

    session: str
    started: datetime
    timezone: str
    config: str | None
    location: Any = None  # the Location switch at Start
    denied: bool = False  # the phone refused the location
    places: list[tuple[str | None, str | None]] = field(default_factory=list)  # (neighbourhood, town)
    listening_s: float | None = None
    listened_s: float = 0.0  # counted from the pauses, for a log with no end event
    cost_usd: float | None = None
    ended: bool = False
    lines: list[Line] = field(default_factory=list)
    markers: list[Marker] = field(default_factory=list)
    candidates: dict[str, Mapping[str, Any]] = field(default_factory=dict)  # by id, in the order flagged
    repeats: list[Mapping[str, Any]] = field(default_factory=list)
    about: dict[str, dict[str, list[Mapping[str, Any]]]] = field(
        default_factory=lambda: defaultdict(lambda: defaultdict(list)))  # candidate id → event → events


def _config(start: Mapping[str, Any]) -> str | None:
    config = start.get("config")
    if not isinstance(config, Mapping):
        return None
    version = config.get("version")
    if not version and isinstance(config.get("text"), str):
        version = hashlib.sha256(config["text"].encode()).hexdigest()[:8]
    return f"{CONFIG_FILE}@{version}" if version else CONFIG_FILE


def _place(place: Any) -> tuple[str | None, str | None] | None:
    """A place event's neighbourhood and town: the city, else the region, else the country."""
    if not isinstance(place, Mapping):
        return None
    town = place.get("city") or place.get("region") or place.get("country")
    neighbourhood = place.get("neighbourhood")
    if not town and not neighbourhood:
        return None
    return (str(neighbourhood) if neighbourhood else None, str(town) if town else None)


def _add_place(places: list[tuple[str | None, str | None]], place: tuple[str | None, str | None]) -> None:
    """Each place once in order. The same town with or without its
    neighbourhood (a better or poorer fix) is one place, the neighbourhood kept."""
    if places:
        last_neighbourhood, last_town = places[-1]
        if last_town == place[1] and (place[0] is None or last_neighbourhood in (None, place[0])):
            places[-1] = (last_neighbourhood or place[0], last_town)
            return
    places.append(place)


def place_name(place: tuple[str | None, str | None]) -> str:
    return ", ".join(dict.fromkeys(p for p in place if p))


def read(events: Iterable[Any], session_id: str | None = None) -> _Log:
    """One pass over the event log. Raises CorpusError when it has no start."""
    events = [e for e in events if isinstance(e, Mapping)]
    start = next((e for e in events if e.get("event") == "session start"), None)
    if start is None:
        raise CorpusError("the event log has no `session start` event" if events else "the event log is empty")
    started = _time(start)
    if started is None:
        raise CorpusError("the `session start` event has no time")
    session = start.get("session") or session_id
    if not isinstance(session, str) or not session:
        raise CorpusError("the `session start` event has no session id")
    log = _Log(session, started, str(start.get("timezone") or DEFAULT_ZONE), _config(start), start.get("location"))
    clocks = _Clocks()
    stream: Any = None  # the stream open now
    paused_at: float | None = None
    gap_from: float | None = None
    listening_from: float | None = 0.0
    last = 0.0

    def gap_ends(at: float) -> None:
        nonlocal gap_from
        if gap_from is not None:
            log.markers.append(Marker("gap", gap_from, at))
            gap_from = None

    for e in events:
        name = e.get("event")
        t = _time(e)
        at = (t - started).total_seconds() if t is not None else last
        last = max(last, at)
        if name == "stt open":
            stream = e.get("stream")
            clocks.open(stream, at)
            gap_ends(at)
        elif name == "stt closed" and e.get("stream") == stream:
            stream = None
        elif name == "stt failed":
            if e.get("stream") == stream:
                stream = None
            if paused_at is None and gap_from is None:
                gap_from = at
        elif name == "page gone":
            if stream is not None:
                clocks.page_gone(stream, at)
            if paused_at is None and gap_from is None:
                gap_from = at
        elif name == "stt finalize":
            clocks.silence(e.get("stream"), e.get("silence_ms"))
        elif name == "page back":
            clocks.page_back(at)
            gap_ends(at)
        elif name == "pause" and paused_at is None:
            gap_ends(at)
            paused_at = at
            if listening_from is not None:
                log.listened_s += at - listening_from
                listening_from = None
        elif name == "resume" and paused_at is not None:
            log.markers.append(Marker("paused", paused_at, at))
            paused_at, listening_from = None, at
        elif name == "session end":
            log.ended = True
            gap_ends(at)
            if paused_at is not None:
                log.markers.append(Marker("paused", paused_at, at))
                paused_at = None
            if listening_from is not None:
                log.listened_s += at - listening_from
                listening_from = None
            log.listening_s = _number(e.get("listening_s"))
            log.cost_usd = _number(e.get("cost_usd"))
        elif name == "location denied":
            log.denied = True
        elif name == "place":
            if (place := _place(e.get("place"))) is not None:
                _add_place(log.places, place)
        elif name == "utterance":
            log.lines.append(_line(e, at, clocks))
        elif name == "candidate" and isinstance(e.get("id"), str):
            log.candidates.setdefault(e["id"], e)
        elif name == "repeat":
            log.repeats.append(e)
        elif name in CARD_EVENTS and isinstance(e.get("id"), str):
            log.about[e["id"]][name].append(e)
        elif name != "decision" and isinstance(e.get("candidate"), str):
            log.about[e["candidate"]][name].append(e)
    if not log.ended:
        if gap_from is not None:
            log.markers.append(Marker("gap", gap_from, None))
        if paused_at is not None:
            log.markers.append(Marker("paused", paused_at, None))
        if listening_from is not None:
            log.listened_s += last - listening_from
    return log


def _line(e: Mapping[str, Any], logged_at: float, clocks: _Clocks) -> Line:
    """An utterance event's line. Its time is its first word's, by its stream's
    clock; with no clock, the time it was logged less its length."""
    start_ms, end_ms = _number(e.get("start_ms")), _number(e.get("end_ms"))
    at = None
    if start_ms is not None:
        at = clocks.said(e.get("stream"), start_ms / 1000)
    if at is None:
        at = logged_at - ((end_ms - start_ms) / 1000 if start_ms is not None and end_ms is not None else 0.0)
    text = " ".join(str(e.get("text") or "").split())
    return Line(str(e.get("id") or ""), label(e.get("stream"), e.get("speaker")), at, text)


# --- Writing the Markdown -----------------------------------------------------------------


def _last(events: Sequence[Mapping[str, Any]], **match: Any) -> Mapping[str, Any] | None:
    return next((e for e in reversed(events) if all(e.get(k) == v for k, v in match.items())), None)


def _p(probs: Any, choice: str) -> float | None:
    p = _number(probs.get(choice)) if isinstance(probs, Mapping) else None
    return None if p is None else round(p, 2)


def _supported(verdict: Mapping[str, Any] | None) -> Any:
    """A verdict's p(supported), else its answer, else its error."""
    if verdict is None:
        return None
    if (p := _p(verdict.get("probs"), "supported")) is not None:
        return p
    if verdict.get("answer"):
        return verdict["answer"]
    return f"failed:{verdict['error']}" if verdict.get("error") else None


def _verified(excerpt: Mapping[str, Any] | None) -> Any:
    """How an excerpt was verified (`page`, `snippet`), or `no` with the reason."""
    if excerpt is None:
        return None
    if excerpt.get("verified"):
        return excerpt.get("method") or "yes"
    return f"no:{excerpt['reason']}" if excerpt.get("reason") else "no"


def _verdict(about: Mapping[str, list[Mapping[str, Any]]]) -> dict[str, Any]:
    """The verdict summary: each fact-finder's outcome, p(same fact),
    p(supported) of each card, how each excerpt was verified and the reason code."""
    summary: dict[str, Any] = {}
    findings = _last(about.get("findings", []))
    failed = findings.get("failed") if findings and isinstance(findings.get("failed"), Mapping) else {}
    missed = findings.get("missed") if findings and isinstance(findings.get("missed"), list) else []
    for finder in FINDERS:
        finding = _last(about.get("finding", []), finder=finder)
        if finder in failed:
            summary[finder] = f"failed:{failed[finder]}"
        elif finder in missed:
            summary[finder] = "missed"
        elif finding is not None:
            outcome = finding.get("outcome")
            summary[finder] = OUTCOMES.get(outcome, outcome)
    if (agreement := _last(about.get("agreement", []))) is not None:
        p = _p(agreement.get("probs"), "same fact")
        summary["same_fact"] = p if p is not None else (
            f"failed:{agreement['error']}" if agreement.get("error") else agreement.get("answer"))
    verdicts = {f: _last(about.get("verdict", []), finder=f) for f in FINDERS}
    if any(verdicts.values()):
        summary["supported"] = [_supported(verdicts[f]) for f in FINDERS]
    excerpts = {f: _last(about.get("excerpt", []), finder=f) for f in FINDERS}
    if any(excerpts.values()):
        summary["verified"] = [_verified(excerpts[f]) for f in FINDERS]
    band, check = _last(about.get("band", [])), _last(about.get("check", []))
    reason = (band or {}).get("reason") or (check or {}).get("reason")
    if reason:
        summary["reason"] = reason
    return summary


def _text(value: Any, prose: type[Text] = Text) -> Any:
    return prose(value) if isinstance(value, str) else value


def _state(check: Mapping[str, Any] | None, about: Mapping[str, list[Mapping[str, Any]]]) -> str | None:
    """How a check ended, when it didn't end with a band: failed, dropped or unfinished."""
    if check is None:
        started = any(about.get(e) for e in ("finding", "findings", "model call", "band"))
        return "unfinished" if started else None
    state = check.get("state")
    if state == "failed":
        why = f" ({check['kind']})" if isinstance(check.get("kind"), str) else ""
        return (f"failed at {check['stage']}" if check.get("stage") else "failed") + why
    if state == "dropped":
        reason = check.get("reason")
        return "dropped" if not reason or str(reason).startswith("silent:") else f"dropped: {reason}"
    return None


def candidate_block(candidate: Mapping[str, Any], about: Mapping[str, list[Mapping[str, Any]]],
                    repeat: Mapping[str, Any] | None, refs: Mapping[str, str]) -> list[tuple]:
    """A candidate's block, from its events. `repeat` is the repeat event of
    an utterance checked anew because the candidate it repeats had failed;
    `refs` gives each utterance's `A2 · 00:04:31`."""
    fields: list[tuple] = [("id", candidate["id"]), ("kind", candidate.get("kind"))]
    if candidate.get("repeat_of"):
        fields.append(("repeat_of", candidate["repeat_of"]))
        if repeat is not None and (p := _number(repeat.get("probability"))) is not None:
            fields.append(("p", round(p, 2)))
    sent = _last(about.get("card sent", []))
    card = None if sent is None or about.get("card withdrawn") else sent
    check = _last(about.get("check", []))
    if card is None:
        fields.append(("shown", "no"))
    else:
        band = card.get("band") or (_last(about.get("band", [])) or {}).get("band")
        fields.append(("shown", band if band in ("plain", "hedged") else "yes"))
        filed = about.get("card filed", [])
        shown = about.get("card shown", [])
        if any(e.get("late") is True for e in filed):
            fields.append(("late", True))
        elif shown or filed:
            fields.append(("late", False))
        ages = [_number(e.get("age_s")) for e in (*shown[:1], card)]
        ages.append(_number((check or {}).get("after_s")))
        if (age := next((a for a in ages if a is not None), None)) is not None:
            fields.append(("check_time_s", round(age, 1)))
        source = card.get("source")
        fields += [("title", _text(card.get("title"))), ("card", _text(card.get("fact"), Wrapped)),
                   ("source", source.get("url") if isinstance(source, Mapping) else source)]
    if (state := _state(check, about)) is not None:
        fields.append(("state", state))
    if check is not None and isinstance(by := check.get("settled_by"), str):
        fields.append(("settled_by", refs.get(by, by)))
    if check is not None and isinstance(disputed := check.get("disputes"), str):
        fields.append(("disputes", disputed))
    restated = {}
    for finder in FINDERS:
        finding = _last(about.get("finding", []), finder=finder)
        if finding is not None and finding.get("restatement"):
            restated[finder] = _text(finding["restatement"], Folded)
    if restated:
        fields.append(("restated", restated))
    if verdict := _verdict(about):
        fields.append(("verdict", verdict))
    kind = "shown" if card is not None else "silent"
    return [*fields, ("mark", None, " | ".join(MARKS[kind])), ("note", None)]


def repeat_block(repeat: Mapping[str, Any]) -> list[tuple]:
    fields: list[tuple] = [("repeat_of", repeat.get("candidate") or UNKNOWN_CANDIDATE)]
    if (p := _number(repeat.get("probability"))) is not None:
        fields.append(("p", round(p, 2)))
    return [*fields, ("mark", None, " | ".join(MARKS["repeat"])), ("note", None)]


def _zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo(DEFAULT_ZONE)


def generate(events: Iterable[Any], session_id: str | None = None) -> str:
    """The corpus Markdown for a recording's event log (every part's events,
    in order). `session_id` names the session when its start event doesn't.

    Raises CorpusError for a log with no session start: an empty one, as a
    stopped recording leaves nothing."""
    log = read(events, session_id)
    header: list[tuple] = [("session", log.session)]
    if log.places:
        header.append(("place", [place_name(p) for p in log.places]))
    else:
        why = "location off" if log.location is False else "location denied" if log.denied else "no place known"
        header.append(("place", [], why))
    if log.listening_s is not None:
        header.append(("listening", duration(log.listening_s)))
    else:
        header.append(("listening", duration(log.listened_s), "no end event: counted from the log"))
    header.append(("config", log.config))
    if log.cost_usd is not None:
        header.append(("cost_usd", round(log.cost_usd, 4)))
    else:
        header.append(("cost_usd", None, "no end event"))
    header += [("status", STATUSES[0], " | ".join(STATUSES)), ("same_speaker", [], "e.g. [[A2, B1]]"),
               ("format", FORMAT)]

    refs = {line.utterance: line.ref() for line in log.lines}
    blocks: dict[str, list[list[tuple]]] = defaultdict(list)
    candidate_of = {c.get("utterance"): c for c in log.candidates.values()}
    for candidate in log.candidates.values():
        repeat = next((r for r in log.repeats if r.get("utterance") == candidate.get("utterance")), None)
        blocks[str(candidate.get("utterance"))].append(
            candidate_block(candidate, log.about[candidate["id"]], repeat, refs))
    for repeat in log.repeats:
        if repeat.get("utterance") not in candidate_of:  # one checked anew has its candidate's block
            blocks[str(repeat.get("utterance"))].append(repeat_block(repeat))
    orphans = [b for u, bs in blocks.items() if u not in refs for b in bs]

    zone = _zone(log.timezone)
    out = [f"# Recording session {log.started.astimezone(zone):%Y-%m-%d %H:%M} ({zone.key})", ""]
    out += _fenced("carl-session", header)
    markers = sorted(log.markers, key=lambda m: m.start)
    said = -1  # the index in `out` of the last transcript line
    for line in log.lines:
        while markers and markers[0].start <= line.at:
            out += _paragraph(markers.pop(0).text())
        if said == len(out) - 1:
            out[said] += " \\"  # a hard line break: the line after it starts a line of its own
        out.append(f"**{line.label}** · {clock(line.at)} · {line.text}".rstrip())
        said = len(out) - 1
        for block in blocks.get(line.utterance, []):
            out += _fenced("carl-candidate", block)
    for block in orphans:
        out += _fenced("carl-candidate", block)
    for marker in markers:
        out += _paragraph(marker.text())
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip("\n") + "\n"


def _paragraph(text: str) -> list[str]:
    return ["", text, ""]


def _fenced(kind: str, fields: Sequence[tuple]) -> list[str]:
    return ["", f"```yaml {kind}", *yaml_lines(fields), "```", ""]


# --- Reading the Markdown back ------------------------------------------------------------

_TRANSCRIPT = re.compile(r"\*\*(?P<label>[^*]+)\*\*\s*·\s*(?P<time>\d+:\d{2}:\d{2})\s*·\s?(?P<text>.*?)"
                         r"(?:\s*\\)?")  # a hard line break's ` \` isn't part of the text
_FENCE = re.compile(r" {0,3}(?P<fence>`{3,}|~{3,})\s*(?P<info>.*)")


@dataclass
class Said:
    """A transcript line as the file has it."""

    line: int  # its line number in the file
    label: str
    time: str
    text: str

    def ref(self) -> str:
        return f"**{self.label}** · {self.time}"


@dataclass
class Block:
    """A fenced `yaml carl-…` block."""

    kind: str  # carl-session, carl-candidate, carl-missed or another the owner wrote
    line: int  # the line number of its opening fence
    data: dict[str, Any]
    after: int  # the index of the transcript line before it, -1 for none
    broken: bool = False  # its YAML couldn't be read, so `data` is empty

    @property
    def role(self) -> str | None:
        """A carl-candidate block's: `candidate` (it has an id) or `repeat`."""
        if self.kind != "carl-candidate" or self.broken:
            return None
        return "candidate" if "id" in self.data else "repeat" if "repeat_of" in self.data else None


@dataclass
class Document:
    said: list[Said] = field(default_factory=list)
    blocks: list[Block] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)  # what couldn't be read

    @property
    def header(self) -> Block | None:
        return next((b for b in self.blocks if b.kind == "carl-session"), None)

    def of(self, role: str) -> list[Block]:
        return [b for b in self.blocks if b.role == role]

    def anchor(self, block: Block) -> tuple[int, str | None]:
        """The index and the reference of the transcript line a block follows."""
        return (block.after, self.said[block.after].ref()) if block.after >= 0 else (-1, None)


def parse(markdown: str) -> Document:
    """The file's transcript lines and blocks. What can't be read goes into `problems`."""
    doc = Document()
    fence: tuple[str, str | None, int, list[str]] | None = None  # the fence, the block kind, its line, its lines
    for n, raw in enumerate(markdown.splitlines(), 1):
        if fence is not None:
            marker, kind, first, lines = fence
            stripped = raw.strip()
            if stripped.startswith(marker) and not stripped.strip(marker[0]):
                if kind is not None:
                    try:
                        block = Block(kind, first, load(lines, first + 1), len(doc.said) - 1)
                    except YamlError as e:
                        doc.problems.append(str(e))
                        block = Block(kind, first, {}, len(doc.said) - 1, broken=True)
                    doc.blocks.append(block)
                fence = None
            else:
                lines.append(raw)
            continue
        if m := _FENCE.fullmatch(raw):
            info = m["info"].split()
            kind = info[1] if len(info) >= 2 and info[0] == "yaml" and info[1].startswith("carl-") else None
            fence = (m["fence"], kind, n, [])
        elif m := _TRANSCRIPT.fullmatch(raw.rstrip()):
            doc.said.append(Said(n, m["label"].strip(), m["time"], m["text"]))
    if fence is not None:
        doc.problems.append(f"line {fence[2]}: the block `{fence[1] or 'fenced'}` isn't closed")
    return doc


def session_of(markdown: str) -> str:
    """The session id in the file's header. Raises CorpusError."""
    header = parse(markdown).header
    session = None if header is None else header.data.get("session")
    if not isinstance(session, str) or not session:
        raise CorpusError("the file has no `yaml carl-session` header with the session id")
    return session


def status(markdown: str) -> Any:
    """The correction status in the file's header, None without one."""
    header = parse(markdown).header
    return None if header is None else header.data.get("status")


def _kinds(doc: Document, expected: Document | None) -> dict[str, str]:
    """Each candidate id's kind of mark, `shown` or `silent`: from the recording
    when it is there, else from the file's own `shown`."""
    kinds = {}
    for block in (expected or doc).of("candidate"):
        kinds[str(block.data.get("id"))] = "silent" if block.data.get("shown") in (None, "no") else "shown"
    return kinds


def started(markdown: str) -> str | None:
    """Why `generate` mustn't overwrite this file, or None when it may: its
    status isn't `not started`, or it holds the owner's work all the same."""
    doc = parse(markdown)
    if doc.problems:
        return f"it can't be read ({doc.problems[0]})"
    if doc.header is None:
        return "it has no `yaml carl-session` header"
    status = doc.header.data.get("status")
    if status != STATUSES[0]:
        return f"its status is {dump(status) or 'empty'}"
    work = []
    if marks := sum(b.data.get("mark") is not None for b in doc.of("candidate") + doc.of("repeat")):
        work.append(_count(marks, "mark"))
    if notes := sum(b.data.get("note") is not None for b in doc.blocks if b.kind != "carl-session"):
        work.append(_count(notes, "note"))
    if missed := sum(b.kind == "carl-missed" for b in doc.blocks):
        work.append(_count(missed, "missed block"))
    if doc.header.data.get("same_speaker"):
        work.append("same_speaker groups")
    return f"its status is `not started`, but it has {', '.join(work)}" if work else None


def describe(markdown: str) -> str:
    """`12 utterances, 3 candidates (2 shown), 1 repeat, 2 of 4 marked, 1 missed, status in progress`."""
    doc = parse(markdown)
    candidates, repeats = doc.of("candidate"), doc.of("repeat")
    shown = sum(b.data.get("shown") not in (None, "no") for b in candidates)
    marked = sum(b.data.get("mark") is not None for b in candidates + repeats)
    missed = sum(b.kind == "carl-missed" for b in doc.blocks)
    status = doc.header.data.get("status") if doc.header else None
    parts = [_count(len(doc.said), "utterance"), f"{_count(len(candidates), 'candidate')} ({shown} shown)",
             _count(len(repeats), "repeat")]
    if marked or missed or status != STATUSES[0]:
        parts += [f"{marked} of {len(candidates) + len(repeats)} marked", f"{missed} missed"]
    return ", ".join(parts) + f", status {dump(status) or 'empty'}"


def _count(n: int, noun: str) -> str:
    return f"{n} {noun}{'s' * (n != 1)}"


# --- Checking a corrected file ------------------------------------------------------------


def check(markdown: str, events: Iterable[Any] | None) -> list[str]:
    """What is wrong with a corrected file, as one line each; empty when it is fine.

    Compared with a fresh `generate` of `events`, the recording's event log:
    candidate ids, the utterance each block follows, repeats, and the
    transcript's speaker labels and times, line by line. Text may differ: the
    owner fixes it around candidates. With `events` None (the recording has
    expired) only the file itself is checked: the marks, `same_speaker`
    against its own labels, the header and the missed blocks.
    """
    doc = parse(markdown)
    problems = list(doc.problems)
    header = doc.header
    expected = None
    if events is not None:
        try:
            session = header.data.get("session") if header else None
            expected = parse(generate(events, session if isinstance(session, str) else None))
        except CorpusError as e:
            problems.append(f"the recording can't be read: {e}")
    problems += _check_header(doc, expected)
    if expected is not None:
        differences, lined_up = _check_transcript(doc, expected)
        problems += differences + _check_candidates(doc, expected, lined_up)
    problems += _check_marks(doc, expected) + _check_missed(doc)
    return problems


def _check_header(doc: Document, expected: Document | None) -> list[str]:
    headers = [b for b in doc.blocks if b.kind == "carl-session"]
    problems = [f"line {b.line}: a block `{b.kind}` Carl doesn't know (it knows {', '.join(BLOCKS)})"
                for b in doc.blocks if b.kind not in BLOCKS]
    problems += [f"line {b.line}: a second `yaml carl-session` header" for b in headers[1:]]
    if not headers:
        return [*problems, "no `yaml carl-session` header"]
    header = headers[0]
    data, where = header.data, f"line {header.line}"
    if header.broken:
        return problems
    if data.get("format") != FORMAT:
        problems.append(f"{where}: format {dump(data.get('format')) or 'missing'}; this Carl reads format {FORMAT}")
    if data.get("status") not in STATUSES:
        problems.append(f"{where}: status {dump(data.get('status')) or 'missing'} isn't one of: {', '.join(STATUSES)}")
    session = expected.header.data.get("session") if expected and expected.header else None
    if session is not None and data.get("session") != session:
        problems.append(f"{where}: session {dump(data.get('session')) or 'missing'} should be {session}")
    labels = {s.label for s in (expected or doc).said}
    groups = data.get("same_speaker")
    if groups is None:
        groups = []
    if not isinstance(groups, list) or not all(isinstance(g, list) for g in groups):
        problems.append(f"{where}: same_speaker should be a list of groups, like [[A2, B1]]")
        return problems
    for group in groups:
        if len(group) < 2:
            problems.append(f"{where}: the same_speaker group {dump(group)} needs two labels or more")
        unknown = [str(g) for g in group if g not in labels]
        if unknown:
            problems.append(f"{where}: same_speaker names {', '.join(unknown)}, which the transcript doesn't have")
    return problems


def _check_transcript(doc: Document, expected: Document) -> tuple[list[str], dict[int, int]]:
    """The transcript's labels and times, line by line, against the
    recording's. Also returns the lines lined up: each of the file's lines
    that stands for one of the recording's, by their indexes, a changed one
    included."""
    got = [(s.label, s.time) for s in doc.said]
    want = [(s.label, s.time) for s in expected.said]
    problems = []
    lined_up = {-1: -1}  # before the transcript

    def where(j: int) -> str:
        return f"line {doc.said[j].line}" if j < len(doc.said) else "at the end"

    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, want, got, autojunk=False).get_opcodes():
        pairs = list(zip(range(i1, i2), range(j1, j2))) if op in ("equal", "replace") else []
        lined_up |= {j: i for i, j in pairs}
        if op == "equal":
            continue
        for i, j in pairs:
            problems.append(f"line {doc.said[j].line}: {doc.said[j].ref()} should be {expected.said[i].ref()}")
        for i in range(i1 + len(pairs), i2):
            problems.append(f"{where(j2)}: the line {expected.said[i].ref()} is missing before here")
        for j in range(j1 + len(pairs), j2):
            problems.append(f"line {doc.said[j].line}: {doc.said[j].ref()} isn't in the recording")
    if len(problems) > MOST_DIFFERENCES:
        problems[MOST_DIFFERENCES:] = [f"… and {len(problems) - MOST_DIFFERENCES} more transcript differences"]
    return problems, lined_up


def _check_candidates(doc: Document, expected: Document, lined_up: Mapping[int, int]) -> list[str]:
    """Candidate ids, repeats and the lines they follow, against the
    recording's, with the transcripts lined up (`_check_transcript`)."""
    problems = []

    def same_place(want: Block, got: Block) -> bool:
        return lined_up.get(got.after) == want.after

    def after(block: Block) -> str:
        ref = expected.anchor(block)[1]
        return f"after {ref}" if ref else "before the transcript"

    want = {str(b.data.get("id")): b for b in expected.of("candidate")}
    seen: set[str] = set()
    for block in doc.of("candidate"):
        cid = str(block.data.get("id"))
        if cid not in want:
            problems.append(f"line {block.line}: {cid} isn't a candidate of this recording")
        elif cid in seen:
            problems.append(f"line {block.line}: a second block for {cid}")
        elif not same_place(want[cid], block):
            problems.append(f"line {block.line}: {cid}'s block should come {after(want[cid])}")
        seen.add(cid)
    problems += [f"{cid} is missing: its block comes {after(b)}" for cid, b in want.items() if cid not in seen]

    repeats = list(expected.of("repeat"))
    for block in doc.of("repeat"):
        match = next((r for r in repeats if same_place(r, block)), None)
        if match is None:
            problems.append(f"line {block.line}: the recording has no repeat here")
            continue
        repeats.remove(match)
        if block.data.get("repeat_of") != match.data.get("repeat_of"):
            problems.append(f"line {block.line}: repeat_of {dump(block.data.get('repeat_of')) or 'missing'} "
                            f"should be {dump(match.data.get('repeat_of'))}")
    problems += [f"the repeat of {dump(r.data.get('repeat_of'))} is missing: its block comes {after(r)}"
                 for r in repeats]
    problems += [f"line {b.line}: a `carl-candidate` block with neither an id nor repeat_of; a candidate "
                 "Carl missed goes in a `yaml carl-missed` block" for b in doc.blocks
                 if b.kind == "carl-candidate" and b.role is None and not b.broken]
    return problems


def _check_marks(doc: Document, expected: Document | None) -> list[str]:
    problems = []
    done = doc.header is not None and doc.header.data.get("status") == "done"
    kinds = _kinds(doc, expected)
    for block in doc.of("candidate") + doc.of("repeat"):
        if block.role == "candidate":
            name = str(block.data.get("id"))
            kind = kinds.get(name) or ("silent" if block.data.get("shown") in (None, "no") else "shown")
            what = {"shown": "a shown card", "silent": "a candidate with no card"}[kind]
        else:
            name, kind, what = f"the repeat of {dump(block.data.get('repeat_of'))}", "repeat", "a repeat"
        mark = block.data.get("mark")
        if mark is None:
            if done:
                problems.append(f"line {block.line}: {name} has no mark, and the status is done")
        elif mark not in MARKS[kind]:
            problems.append(f"line {block.line}: {name} has the mark {dump(mark)}; {what}'s mark is one of: "
                            f"{', '.join(MARKS[kind])}")
    return sorted(problems, key=_line_number)


def _check_missed(doc: Document) -> list[str]:
    problems = []
    for block in doc.blocks:
        if block.kind != "carl-missed" or block.broken:
            continue
        where = f"line {block.line}"
        if block.data.get("kind") not in MISSED_KINDS:
            problems.append(f"{where}: a missed block's kind is {' or '.join(MISSED_KINDS)}, not "
                            f"{dump(block.data.get('kind')) or 'empty'}")
        should_say = block.data.get("should_say")
        if not isinstance(should_say, str) or not should_say.strip():
            problems.append(f"{where}: a missed block needs should_say: what the card should have said")
        if block.after < 0:
            problems.append(f"{where}: a missed block goes under the utterance Carl should have caught")
    return problems


def _line_number(problem: str) -> int:
    m = re.match(r"line (\d+):", problem)
    return int(m[1]) if m else 0
