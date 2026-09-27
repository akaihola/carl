"""Can't hear, can't check and the failure log (spec section 10).

**The failure log** (`FailureLog`, `Sessions.failures`) holds the moments
Carl couldn't hear or couldn't check, with no conversation content and no
free-text provider message, under `failures/` in the store: one JSONL file a
day (UTC), rewritten whole on each write, since this one instance owns them.
The bucket's 30-day rule deletes them. Each line is either

- an entry (`type: "entry"`): the time, the session id, the stage
  (`speech-to-text`, `decision`, `settle`, `fact-finding A`, `fact-finding
  B`, `fact-checking`, `connection`, `mic`; `fact-finding` for a candidate
  refused with `overload` or timed out while both fact-finders searched),
  the kind (`timeout`, `unavailable`, `rate-limited`, `bad-output`,
  `dropped`, `overload`, `lost-in-restart`, `no-audio`, `mic-lost`), the
  provider and model id, the HTTP status and the provider's error code, and
  Carl's candidate id; or
- an outage (`type: "outage"`), written when it starts and again when it
  ends, under the same id: the problem (`cant_hear`, `cant_check`), its
  reason code, the stage, the start and the end, and for the decision model
  the utterances dropped since it last worked. Outages the page saw on its
  own (`source: "page"`) come from its buffer after a reconnect.

A recording session's event log gets a copy of each (`failure`, `outage`),
a failed call's with the provider's full error text.

**The indicator** (`Health`, one per session) is "Can't hear" while any of
these reasons holds, in the order their code wins:

- `connection`: the page's connection dropped (it closed, or was silent for
  `silence_s`), until audio arrives on the page's new connection (or at once
  while paused). The planned handover is a rejoin on a second socket while
  the first is still open, so it never drops.
- `mic-lost`: the page reported its microphone lost, until it reports it
  back.
- `no-audio`: while listening, with the page connected and its microphone
  live, no audio chunk for `outages.no_audio_s`, until the next one.
- `stt-reopening`: speech-to-text dropped, until a new stream is open.

Pause and long silence are none of these. It is "Can't check" while a stage
is down: the decision model after `outages.decision_failures` failed calls
in a row (decision and settle calls counted together), fact-finding or
fact-checking after `outages.check_failures` failed candidates in a row. A
candidate fails at fact-finding only when every fact-finder fails on it (or
it times out while they search), and at fact-checking only when a failed
call leaves it without a band (or it times out there). `overload` counts
for nothing. A stage clears on its first success. "Can't hear" wins. The
page gets `indicator` when the state changes and after `start` and
`rejoin`; the recording mark (`recording` in the `session` message) goes off
while no audio can reach the server or storage.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .session import Session
    from .storage import Store

log = logging.getLogger(__name__)

CANT_HEAR, CANT_CHECK = "cant_hear", "cant_check"
# The reason codes, each with its problem and failure-log stage, in the order they win.
REASONS: dict[str, tuple[str, str]] = {
    "connection": (CANT_HEAR, "connection"),
    "mic-lost": (CANT_HEAR, "mic"),
    "no-audio": (CANT_HEAR, "mic"),
    "stt-reopening": (CANT_HEAR, "speech-to-text"),
    "decision": (CANT_CHECK, "decision"),
    "fact-finding": (CANT_CHECK, "fact-finding"),
    "fact-checking": (CANT_CHECK, "fact-checking"),
}
# While these hold, no audio reaches the server, so nothing new is recorded.
DEAF = ("connection", "mic-lost", "no-audio")
# The kinds of the failure-log entry that starts an outage, where Carl sees no failed call itself.
STARTS = {"connection": "dropped", "mic-lost": "mic-lost", "no-audio": "no-audio"}
# What a page event may carry into the logs: short strings only.
PAGE_EVENT_KEYS = ("kind", "start", "end", "at", "detail", "state", "id")


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class FailureLog:
    """The failure log in the store, `failures/<UTC date>.jsonl`.

    `add` is synchronous and never raises: it queues the record and a task
    writes it. A write that fails keeps its records queued for the next one;
    `flush` writes whatever is queued, as at shutdown.
    """

    def __init__(self, store: Store) -> None:
        self.store = store
        self.days: dict[str, list[str]] = {}  # each day's lines as last written
        self.pending: dict[str, list[str]] = {}
        self.lock = asyncio.Lock()
        self.task: asyncio.Task | None = None

    @staticmethod
    def key(day: str) -> str:
        return f"failures/{day}.jsonl"

    def add(self, record: dict[str, Any]) -> None:
        day = str(record.get("time") or now_iso())[:10]
        self.pending.setdefault(day, []).append(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        if self.task is None or self.task.done():
            self.task = loop.create_task(self.flush())

    async def flush(self) -> None:
        async with self.lock:
            while self.pending:
                day = min(self.pending)
                lines = self.pending.pop(day)
                try:
                    if day not in self.days:
                        old = await self.store.get(self.key(day))
                        self.days[day] = old.decode().splitlines(keepends=True) if old else []
                    await self.store.put(self.key(day), "".join(self.days[day] + lines).encode())
                except Exception:  # noqa: BLE001 - kept queued for the next write
                    log.warning("couldn't write the failure log for %s; %d records wait", day, len(lines),
                                exc_info=True)
                    self.pending[day] = lines + self.pending.get(day, [])
                    return
                self.days[day] += lines
            for day in sorted(self.days)[:-1]:  # only the latest day is still written to
                del self.days[day]

    async def records(self, day: str) -> list[dict[str, Any]]:
        """The day's records as stored."""
        data = await self.store.get(self.key(day))
        return [json.loads(line) for line in data.decode().splitlines()] if data else []


@dataclass
class Outage:
    id: str
    reason: str
    start: str
    detail: str | None = None
    skipped: int = 0


class Health:
    """One session's listening indicator: its open outages, the failures in a
    row that open "Can't check", and what the page was last told."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.open: dict[str, Outage] = {}
        self.in_a_row: Counter[str] = Counter()
        self.dropped = 0  # utterances dropped since the decision model last worked
        self.outages = 0
        self.shown: tuple[str | None, str | None] | None = None  # the indicator the page was last sent
        self.last_audio = time.monotonic()

    # --- The state --------------------------------------------------------------------

    @property
    def deaf(self) -> bool:
        """No audio can reach the server."""
        return any(reason in self.open for reason in DEAF)

    def indicator(self) -> tuple[str | None, str | None]:
        """The problem (`cant_hear`, `cant_check` or None) and its reason code."""
        for reason, (problem, _) in REASONS.items():
            if reason in self.open:
                return problem, reason
        return None, None

    def message(self) -> dict[str, Any]:
        """The `indicator` message, which the page is then taken to have."""
        self.shown = self.indicator()
        problem, reason = self.shown
        return {"type": "indicator", "problem": problem, "reason": reason}

    def begin(self, reason: str, detail: str | None = None, skipped: int = 0, **entry: Any) -> None:
        """An outage starts, unless it already holds. A reason with no failed
        call of its own gets its failure-log entry here."""
        if reason in self.open:
            return
        session = self.session
        self.outages += 1
        outage = self.open[reason] = Outage(f"{session.id}-{self.outages}", reason, now_iso(), detail, skipped)
        if reason in STARTS:
            session.failure(REASONS[reason][1], STARTS[reason], **entry)
        log.warning("session %s: %s (%s)", session.id, REASONS[reason][0], reason)
        self.record(outage)
        self.changed()

    def end(self, reason: str) -> None:
        outage = self.open.pop(reason, None)
        if outage is None:
            return
        log.info("session %s: %s is over", self.session.id, reason)
        self.record(outage, end=now_iso())
        self.changed()

    def end_all(self) -> None:
        """At End: every outage still open ends."""
        for reason in list(self.open):
            self.end(reason)

    def record(self, outage: Outage, end: str | None = None) -> None:
        problem, stage = REASONS[outage.reason]
        record = {"id": outage.id, "problem": problem, "reason": outage.reason, "stage": stage,
                  "start": outage.start, "end": end}
        if outage.reason == "decision":
            record["utterances_skipped"] = outage.skipped
        if outage.detail:
            record["detail"] = outage.detail
        self.session.sessions.failures.add({"type": "outage", "time": now_iso(), "session": self.session.id,
                                            **record})
        self.session.log("outage", **record)

    def changed(self) -> None:
        """Tell the page what changed: the indicator, and the recording mark."""
        try:
            asyncio.get_running_loop()
        except RuntimeError:  # no event loop: nobody to tell
            return
        self.session.spawn(self.tell())

    async def tell(self) -> None:
        session = self.session
        if session.state == "ended":
            return
        if self.indicator() != self.shown:
            await session.send(self.message())
        if session.recording != session.recording_sent:
            await session.send(session.state_message())

    # --- Can't hear ----------------------------------------------------------------

    def audio(self) -> None:
        """An audio chunk arrived: audio flows end to end again."""
        self.last_audio = time.monotonic()
        for reason in ("no-audio", "connection"):
            if reason in self.open:
                self.end(reason)

    def mic(self, state: str, detail: str | None) -> None:
        if state == "lost":
            self.end("no-audio")
            self.begin("mic-lost", detail)
        elif state == "back":
            self.last_audio = time.monotonic()
            self.end("mic-lost")

    def expects_audio(self) -> bool:
        """Listening, with the page connected and its microphone live."""
        session = self.session
        return session.state == "listening" and session.link is not None and not self.deaf

    async def watch_audio(self) -> None:
        """"Can't hear" after `no_audio_s` without an audio chunk while audio is expected."""
        limit = self.session.config.outages.no_audio_s
        while self.session.state != "ended":
            left = self.last_audio + limit - time.monotonic()
            if left > 0:
                await asyncio.sleep(left)
            elif not self.expects_audio():
                await asyncio.sleep(min(1.0, limit))
            else:
                self.begin("no-audio")

    # --- Can't check -----------------------------------------------------------------

    def call(self, ok: bool, dropped: bool = False) -> None:
        """A decision or settle call's outcome. A failed decision call drops its utterance."""
        if ok:
            self.in_a_row["decision"] = 0
            self.dropped = 0
            self.end("decision")
            return
        self.in_a_row["decision"] += 1
        self.dropped += dropped
        if (outage := self.open.get("decision")) is not None:
            outage.skipped = self.dropped
        elif self.in_a_row["decision"] >= self.session.config.outages.decision_failures:
            self.begin("decision", skipped=self.dropped)

    def candidate(self, stage: str, ok: bool) -> None:
        """A candidate's outcome at `fact-finding` or `fact-checking`."""
        if ok:
            self.in_a_row[stage] = 0
            self.end(stage)
            return
        self.in_a_row[stage] += 1
        if self.in_a_row[stage] >= self.session.config.outages.check_failures:
            self.begin(stage)

    # --- The page's buffer ------------------------------------------------------------

    def page_events(self, events: Any) -> None:
        """What the page buffered while it couldn't tell the server: a
        connection gap and a lost microphone are outages in the failure log;
        these and the rest (hidden, wake lock, a card that failed to render)
        go to the event log."""
        if not isinstance(events, list):
            return
        session = self.session
        for raw in events[:200]:
            if not isinstance(raw, dict):
                continue
            event = {k: str(raw[k])[:64] for k in PAGE_EVENT_KEYS if isinstance(raw.get(k), str | int | float)}
            session.log("page event", **event)
            reason = {"gap": "connection", "mic-lost": "mic-lost"}.get(event.get("kind", ""))
            if reason is None:
                continue
            self.outages += 1
            problem, stage = REASONS[reason]
            record = {"id": f"{session.id}-{self.outages}", "problem": problem, "reason": reason, "stage": stage,
                      "start": event.get("start"), "end": event.get("end"), "source": "page"}
            if event.get("detail"):
                record["detail"] = event["detail"]
            session.sessions.failures.add({"type": "outage", "time": now_iso(), "session": session.id, **record})
