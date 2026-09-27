"""Sessions on the server (spec sections 1, 4, 9 and 10).

A session runs from Start to End. The server is its source of truth: the
page's audio goes to speech-to-text and, in a recording session, to the
recording; speech-to-text's final words become utterances; the stream's
open time is charged to the month's cost. A session outlives its page's
connection for the reconnect grace period, with the stream kept open, so
the page can rejoin it.

The server is also the source of truth for the session's fact cards
(section 8): it keeps each card it sent with its state and the times the page
reported, and sends them all again after a rejoin, withdrawn cards left out.

Each session's listening indicator ("Can't hear", "Can't check") and its
failures are `carl.outages`'s: `Session.health` and `Sessions.failures`. Its
state is saved as it changes, so a restarted server can resume it
(`carl.resume`): `Session.keep_saved`, `Session.suspend` at a shutdown and
`Session.carry_on` after one.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import re
import secrets
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

from . import costs as costs_module
from .config import Config
from .costs import Costs
from .link import Link
from .outages import FailureLog, Health, now_iso
from .prompts import Prompt
from .recording import Recorder
from .storage import Store
from .stt import SpeechToText, SttError, SttEvent, SttStream
from .utterances import Splitter, Utterance

log = logging.getLogger(__name__)

SESSION_ID = re.compile(r"\d{8}T\d{6}Z-[0-9a-f]{6}")
SPEECH_PULSE_S = 0.5  # at most one `speech` message this often
KEEPALIVE_S = 10.0  # Soniox wants one at least every 20 s without audio
COST_EVERY_S = 60.0  # charge the stream's time to the month this often
# A dropped stream reopens at once, then after 1, 2, 4… up to 30 s while it keeps failing.
REOPEN_BACKOFF_S = (0, 1, 2, 4, 8, 16, 30)
# Soniox ends a stream after 300 minutes: one this old is replaced at its next segment end.
ROTATE_AFTER_S = 280 * 60
SAVE_EVERY_S = 3.0  # the session's state is saved at most this often, but at once after a change that matters
# Soniox finalises nothing while no audio arrives, and advises about 200 ms of
# silence before a manual finalise. It goes to speech-to-text only, never to
# the recording.
FINALIZE_SILENCE = b"\0" * 6400
CHECKS_AT_END_S = 25.0  # End waits this long for running decisions and checks, so they are recorded and charged

CardState = Literal["ready", "on screen", "card history", "withdrawn"]
# A card only moves forward, in this order. A ready card can instead be
# withdrawn, which is final.
CARD_STATES: tuple[CardState, ...] = ("ready", "on screen", "card history")


def new_session_id() -> str:
    return f"{datetime.now(UTC):%Y%m%dT%H%M%SZ}-{secrets.token_hex(3)}"


def iso_time(t: float) -> str:
    """Wall time `t` in ISO 8601 UTC with milliseconds: `2026-09-27T18:04:31.200Z`."""
    return datetime.fromtimestamp(t, UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


@dataclass
class Marker:
    """A stream boundary in the decision context: "(paused)" or "(gap)"."""

    kind: Literal["paused", "gap"]
    time: float


@dataclass
class Heard:
    """An utterance with Carl's id and its place in the session."""

    id: str
    stream: int
    utterance: Utterance
    time: float  # when its last word ended, in session wall time

    def event(self) -> dict[str, Any]:
        u = self.utterance
        return {
            "id": self.id, "stream": self.stream, "speaker": u.speaker, "text": u.text,
            "start_ms": u.start_ms, "end_ms": u.end_ms, "words": [asdict(w) for w in u.words],
        }


@dataclass
class Card:
    """A fact card sent to the page, with its state and the times the page reported.

    It is `ready` once sent, `on screen` when the page reports it shown and
    in the `card history` when the page reports it filed: tapped away, or
    late. The state only moves forward, so a report that arrives after a
    later one (the page queues them while it is away) is recorded and
    changes nothing. The candidate's own state follows the card's. A card
    settled at the table before it was shown is `withdrawn` for good, and
    its candidate `dropped`.
    """

    id: str  # the candidate's, C3
    content: dict[str, Any]  # the `card` message's card, `age_s` aside
    utterance_time: float  # when its utterance ended, in session wall time
    candidate: Any = None
    state: CardState = "ready"
    sent: float | None = None
    shown_at: str | None = None  # the page's time, as it reported it
    shown_received: float | None = None  # the server's
    filed_at: str | None = None
    filed_received: float | None = None
    late: bool | None = None

    def message(self, now: float) -> dict[str, Any]:
        """The card as the page gets it. `age_s` is the time since its
        utterance ended by the server's clock, so a phone clock that is off
        doesn't move the late-card cut-off, and never below 0."""
        return self.content | {"age_s": max(0.0, round(now - self.utterance_time, 1))}

    def move(self, state: CardState) -> None:
        if self.state == "withdrawn":
            return
        if CARD_STATES.index(state) > CARD_STATES.index(self.state):
            self.state = state
        if self.candidate is not None:
            self.candidate.state = self.state


@dataclass
class Summary:
    """The "Session ended" summary."""

    listening_s: float
    cost_usd: float
    cost_eur: float
    recording: Literal["kept", "stopped", "none"]
    cards: int | None = None
    month_eur: float | None = None

    def message(self, session_id: str) -> dict[str, Any]:
        return {"type": "ended", "session": session_id, "summary": asdict(self)}


@dataclass
class StreamRun:
    """One speech-to-text stream: labels are only valid within it."""

    index: int
    stream: SttStream
    opened: float
    charged_until: float
    reader: asyncio.Task | None = None
    splitter: Splitter | None = None


@dataclass
class Session:
    sessions: Sessions
    id: str
    record: bool
    started: float = field(default_factory=time.time)
    state: Literal["listening", "paused", "ended"] = "listening"
    link: Link | None = None
    recorder: Recorder | None = None
    recording_stopped: bool = False
    run: StreamRun | None = None
    streams: int = 0
    heard: list[Heard | Marker] = field(default_factory=list)
    utterance_count: int = 0
    cost_usd: float = 0.0
    listening_s: float = 0.0
    listening_since: float | None = None
    last_pulse: float = 0.0
    tasks: set[asyncio.Task] = field(default_factory=set)
    checks: set[asyncio.Task] = field(default_factory=set)  # decisions and checks: End waits for them
    grace: asyncio.Task | None = None
    summary: Summary | None = None
    timezone: str = "UTC"  # the phone's, from `start`
    place: Any = None  # the current place name, set by carl.location (step 3)
    candidates: list[Any] = field(default_factory=list)  # set by carl.decision (step 3)
    cards: dict[str, Card] = field(default_factory=dict)  # every card sent, by id, in the order sent
    deciding: set[asyncio.Task] = field(default_factory=set)  # decision calls still running
    disputing: dict[str, str] = field(default_factory=dict)  # utterance id → the on-screen candidate it disputes
    health: Health = field(init=False)
    recording_sent: bool | None = None  # the recording mark the page was last sent
    start_id: str = ""  # the page's own id for its Start
    saver: asyncio.Task | None = None
    save_now: asyncio.Event = field(default_factory=asyncio.Event)
    saving_stopped: bool = False
    suspended: bool = False  # saved at a shutdown for the next instance, not ended
    open_on_rejoin: bool = False  # resumed after a restart: its stream opens when the page is back

    def __post_init__(self) -> None:
        self.health = Health(self)

    @property
    def config(self) -> Config:
        return self.sessions.config

    @property
    def recording(self) -> bool:
        """Audio is actually being written: a recording that isn't stopped, not
        paused, with audio reaching the server and the writes reaching storage."""
        return (self.recorder is not None and self.recorder.active and self.state == "listening"
                and not self.health.deaf and not getattr(self.recorder, "failing", False))

    def state_message(self) -> dict[str, Any]:
        self.recording_sent = self.recording
        return {"type": "session", "session": self.id, "state": self.state, "recording": self.recording}

    def log(self, event: str, **fields: Any) -> None:
        if self.recorder is not None:
            self.recorder.log(event, **fields)

    def failure(self, stage: str, kind: str, *, record: Any = None, candidate: str | None = None,
                provider: str | None = None, model: str | None = None, **fields: Any) -> None:
        """A moment Carl couldn't hear or check, for the failure log (spec
        section 10): the stage (`decision`, `settle`, `fact-finding A`…), the
        kind (`timeout`, `bad-output`, `overload`…), the provider and model,
        the HTTP status and error code from a failed call's `record`, and the
        candidate's id; never conversation content or the provider's text. A
        recording's event log gets a copy with the provider's full error text."""
        entry: dict[str, Any] = {"stage": stage, "kind": kind.replace(" ", "-"), "provider": provider,
                                 "model": model, "status": None, "code": None, "candidate": candidate}
        if record is not None:
            entry |= {"provider": record.provider, "model": record.model, "status": record.status,
                      "code": record.error_code}
        self.sessions.failures.add({"type": "entry", "time": now_iso(), "session": self.id, **entry, **fields})
        text = {"error_text": record.error_text} if record is not None and record.error_text else {}
        self.log("failure", **entry, **fields, **text)

    def spawn(self, coro) -> asyncio.Task:
        task = asyncio.create_task(coro)
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        return task

    def spawn_check(self, coro) -> asyncio.Task:
        """A task End waits for: a decision call, or a candidate's check."""
        task = self.spawn(coro)
        self.checks.add(task)
        task.add_done_callback(self.checks.discard)
        return task

    # --- Start, audio, pause, end ---------------------------------------------------

    async def begin(self, header: dict[str, Any]) -> None:
        if self.record:
            self.recorder = Recorder(self.sessions.store, self.id)
            self.log("session start", session=self.id, record=True, **header, **self.sessions.build_info())
            self.recorder.on_failing = self.health.changed
            self.spawn(self.recorder.run())
        self.listening_since = time.time()
        self.health.last_audio = time.monotonic()
        self.spawn(self.health.watch_audio())
        self.start_saving()
        await self.open_stream()

    async def carry_on(self, saved_at: str | None = None) -> None:
        """Carry on a session rebuilt from its saved state after a restart
        (`carl.resume`): its recording continues under the same prefix, a
        check the restart lost fails as `lost-in-restart`, and it waits the
        grace period for its page, "Can't hear" meanwhile. Its stream opens
        when the page rejoins."""
        if self.record and not self.recording_stopped:
            self.recorder = Recorder(self.sessions.store, self.id)
            await self.recorder.continue_after()
            self.recorder.on_failing = self.health.changed
            self.log("session resumed", after_restart=True, saved=saved_at, state=self.state)
            self.spawn(self.recorder.run())
        self.heard.append(Marker("gap", time.time()))  # a new stream, fresh labels
        for candidate in self.candidates:
            if (stage := {"finding": "fact-finding", "checking": "fact-checking"}.get(candidate.state)) is not None:
                self.failure(stage, "lost-in-restart", candidate=candidate.id)
                candidate.state = "failed"
                self.log("check", candidate=candidate.id, state="failed", stage=stage, kind="lost-in-restart")
        if self.state == "listening":
            self.listening_since = time.time()
            self.open_on_rejoin = True
        self.health.begin("connection", detail="restart")
        self.spawn(self.health.watch_audio())
        self.grace = self.spawn(self.wait_for_page())
        self.start_saving()
        self.save_soon()

    # --- Saving the state -----------------------------------------------------------

    def start_saving(self) -> None:
        if self.sessions.states is not None and self.saver is None:
            self.saver = self.spawn(self.keep_saved())

    def save_soon(self) -> None:
        """A change that matters: save the state at once."""
        if self.saver is not None:
            self.save_now.set()

    async def keep_saved(self) -> None:
        """Save the state as it changes, at most every SAVE_EVERY_S unless
        `save_soon` asks for it at once."""
        while not self.saving_stopped:
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self.save_now.wait(), SAVE_EVERY_S)
            self.save_now.clear()
            if not self.saving_stopped:
                await self.sessions.states.save(self)

    async def stop_saving(self) -> None:
        """Stop saving, and wait for a save under way, so none lands after a delete."""
        self.saving_stopped = True
        if self.saver is not None:
            self.save_now.set()
            with contextlib.suppress(asyncio.CancelledError):
                await self.saver
            self.saver = None

    async def suspend(self) -> None:
        """At a server shutdown: save the session for the next instance to
        resume, rather than end it. Its stream closes and its recording is
        written out; checks still running are lost, and fail as
        `lost-in-restart` when it resumes."""
        if self.state == "ended" or self.suspended:
            return
        self.suspended = True
        if self.state == "listening":
            self.count_listening()
        await self.stop_saving()
        run, self.run = self.run, None
        await self.close_run(run, finalize=False)
        self.health.end_all()
        self.log("session suspended", reason="server shutdown")
        if self.sessions.states is not None:
            await self.sessions.states.save(self, force=True)
        if self.recorder is not None:
            self.recorder.audio_break()
            await self.recorder.close()
        for task in list(self.tasks):
            if task is not asyncio.current_task():
                task.cancel()
        log.info("session %s saved for the next instance", self.id)

    async def audio(self, chunk: bytes) -> None:
        if self.state != "listening" or self.suspended:
            return
        self.health.audio()
        if self.recorder is not None:
            self.recorder.audio(chunk)
        if self.run is not None:
            try:
                await self.run.stream.send_audio(chunk)
            except SttError as e:
                self.stream_failed(self.run, e)

    async def pause(self) -> None:
        if self.state != "listening":
            return
        self.state = "paused"
        self.count_listening()
        self.log("pause")
        self.save_soon()
        for reason in ("no-audio", "stt-reopening", "connection"):  # paused, nothing is heard anyway
            if reason != "connection" or self.link is not None:
                self.health.end(reason)
        if self.recorder is not None:
            self.recorder.audio_break()
        await self.close_stream(finalize=True)
        self.heard.append(Marker("paused", time.time()))

    async def resume(self) -> None:
        if self.state != "paused":
            return
        self.state = "listening"
        self.listening_since = time.time()
        self.health.last_audio = time.monotonic()
        self.log("resume")
        self.open_on_rejoin = False
        self.save_soon()
        await self.open_stream()

    async def end(self, reason: str) -> Summary:
        if self.summary is not None:
            return self.summary
        was_listening = self.state == "listening"
        self.state = "ended"
        if was_listening:
            self.count_listening()
        await self.stop_saving()
        if self.grace is not None and self.grace is not asyncio.current_task():
            self.grace.cancel()
        await self.close_stream(finalize=was_listening)
        # Decisions still running, incl. those on the utterances the finalise
        # just gave, and checks, incl. those the decisions start meanwhile.
        deadline = time.monotonic() + CHECKS_AT_END_S
        while self.checks and (left := deadline - time.monotonic()) > 0:
            await asyncio.wait(set(self.checks), timeout=left)
        if self.recorder is not None:
            self.recorder.audio_break()
        self.health.end_all()
        self.log("session end", reason=reason, listening_s=round(self.listening_s, 1),
                 cost_usd=round(self.cost_usd, 6), utterances=self.utterance_count, cards=len(self.cards))
        recording: Literal["kept", "stopped", "none"] = "stopped" if self.recording_stopped else "none"
        if self.recorder is not None:
            await self.recorder.close()
            recording = "kept"
        for task in list(self.tasks):
            if task is not asyncio.current_task():
                task.cancel()
        if self.sessions.states is not None:
            await self.sessions.states.delete(self.id)
        month = await self.sessions.month_eur()
        # The cards sent and not withdrawn; "—" on the page with no checks.
        cards = None if self.sessions.checker is None else sum(c.state != "withdrawn" for c in self.cards.values())
        self.summary = Summary(round(self.listening_s, 1), round(self.cost_usd, 6),
                               round(costs_module.to_eur(self.config, self.cost_usd), 6), recording, cards, month)
        log.info("session %s ended (%s) after %.0f s listening", self.id, reason, self.listening_s)
        self.sessions.finished(self)
        return self.summary

    async def stop_recording(self) -> None:
        """The one-way stop: delete everything recorded so far, and record nothing more."""
        self.recording_stopped = True
        self.save_soon()
        if self.recorder is not None:
            deleted = await self.recorder.stop_and_delete()  # kept until the delete succeeds
            self.recorder = None
        else:  # a resent stop: make sure nothing is left
            deleted = await self.sessions.store.delete_prefix(f"recordings/{self.id}/")
        log.info("session %s: recording stopped, %d objects deleted", self.id, deleted)

    def count_listening(self) -> None:
        if self.listening_since is not None:
            self.listening_s += time.time() - self.listening_since
            self.listening_since = None

    # --- The page's connection -------------------------------------------------------

    async def attach(self, link: Link) -> None:
        if self.grace is not None:
            self.grace.cancel()
            self.grace = None
            self.log("page back")
        self.link = link
        self.health.last_audio = time.monotonic()
        if self.state != "listening":  # otherwise it clears once audio arrives on the new connection
            self.health.end("connection")
        elif self.open_on_rejoin:  # resumed after a restart: a stream only now there is a page to hear
            self.open_on_rejoin = False
            self.spawn(self.open_stream())

    async def detach(self, link: Link) -> None:
        """The page's connection dropped: keep the session for the grace period."""
        if self.link is not link or self.state == "ended" or self.suspended:
            return
        self.link = None
        self.log("page gone")
        self.health.end("no-audio")
        self.health.begin("connection", silent=link.dropped)
        if self.recorder is not None:
            self.recorder.audio_break()
        if self.state == "listening":
            self.spawn(self.finalize(self.run))  # so the last words before the drop become final
        self.grace = self.spawn(self.wait_for_page())

    async def wait_for_page(self) -> None:
        deadline = time.monotonic() + self.config.connection.reconnect_grace_s
        while (left := deadline - time.monotonic()) > 0:
            await asyncio.sleep(min(KEEPALIVE_S, left))
            if self.run is not None and time.monotonic() < deadline:
                with contextlib.suppress(SttError):
                    await self.run.stream.keepalive()
        self.grace = None
        await self.end("page gone")

    async def send(self, message: dict[str, Any]) -> None:
        if self.link is not None:
            with contextlib.suppress(ConnectionError):
                await self.link.send(message)

    # --- Cards -----------------------------------------------------------------------

    async def send_card(self, card: Card) -> None:
        """Send a card to the page. It is kept first, so a page that is away
        gets it in the `cards` after its rejoin."""
        card.sent = now = time.time()
        self.cards[card.id] = card
        card.move("ready")
        self.save_soon()
        message = card.message(now)
        self.log("card sent", page=self.link is not None, **message)
        await self.send({"type": "card", "card": message})

    async def withdraw_card(self, card_id: str, **fields: Any) -> bool:
        """Withdraw a card sent but not yet shown: the page removes it. A card
        on screen or in the card history stays as it is. False if it can't
        be withdrawn."""
        card = self.cards.get(card_id)
        if card is None or card.state != "ready":
            return False
        card.state = "withdrawn"
        self.save_soon()
        self.log("card withdrawn", id=card_id, age_s=round(time.time() - card.utterance_time, 1), **fields)
        await self.send({"type": "card_withdrawn", "id": card_id})
        return True

    def card_reported(self, report: Literal["shown", "filed"], card_id: str, at: Any, late: bool = False) -> None:
        """The page's `card_shown` or `card_filed`, with the page's time `at`
        and, for a filed card, whether it was late. The first report of each
        kind sets the card's times; every report is recorded."""
        received = time.time()
        at = at[:64] if isinstance(at, str) else None
        fields: dict[str, Any] = {"id": card_id, "at": at, "received": iso_time(received)}
        if report == "filed":
            fields["late"] = late
        card = self.cards.get(card_id)
        if card is None:
            log.warning("session %s: card_%s for a card it never sent: %.20r", self.id, report, card_id)
            self.log(f"card {report}", **fields, state=None)
            return
        if report == "shown":
            if card.shown_received is None:
                card.shown_at, card.shown_received = at, received
            card.move("on screen")
        else:
            if card.filed_received is None:
                card.filed_at, card.filed_received, card.late = at, received, late
            card.move("card history")
        self.save_soon()
        self.log(f"card {report}", **fields, age_s=round(received - card.utterance_time, 1), state=card.state)

    def cards_message(self) -> dict[str, Any]:
        """The whole screen again, for a page that rejoins: the card on screen
        (shown and not filed), the cards waiting for the screen (sent, neither
        shown nor filed) in utterance order, and the card history (filed)
        newest first by utterance time. Should the page have shown two cards
        without filing the first, the one shown last is on screen and the
        other in the history."""
        now = time.time()
        by_time = sorted(self.cards.values(), key=lambda c: c.utterance_time)
        on_screen = [c for c in by_time if c.state == "on screen"]
        current = max(on_screen, key=lambda c: c.shown_received or 0.0, default=None)
        return {
            "type": "cards",
            "current": None if current is None else current.message(now),
            "waiting": [c.message(now) for c in by_time if c.state == "ready"],
            "history": [c.message(now) for c in reversed(by_time)
                        if c.state == "card history" or (c.state == "on screen" and c is not current)],
        }

    async def send_cards(self) -> None:
        """Send the whole screen again after a rejoin, if there is anything on it."""
        message = self.cards_message()
        if message["current"] is None and not message["waiting"] and not message["history"]:
            return
        self.log("cards sent", current=message["current"] and message["current"]["id"],
                 waiting=[c["id"] for c in message["waiting"]], history=[c["id"] for c in message["history"]])
        await self.send(message)

    # --- Speech-to-text --------------------------------------------------------------

    async def open_stream(self, attempt: int = 0) -> None:
        """Open a speech-to-text stream; if it fails, "Can't hear" while it is
        tried again, backing off (`REOPEN_BACKOFF_S`)."""
        run = await self.new_run()
        if run is None:
            self.health.begin("stt-reopening")
            self.spawn(self.reopen(attempt + 1))
            return
        self.run = run
        self.health.end("stt-reopening")

    async def new_run(self) -> StreamRun | None:
        """A new stream with its reader, or None if it didn't open (recorded as a failure)."""
        self.streams += 1
        index = self.streams
        stage = self.config.stages.speech_to_text
        try:
            stream = await self.sessions.stt.open(stage.params.get("language_hints", ["fi", "en"]))
        except SttError as e:
            log.warning("session %s: speech-to-text didn't open: %s", self.id, e)
            self.log("stt failed", stream=index, kind=e.kind, detail=e.detail)
            self.failure("speech-to-text", e.kind, provider=stage.provider, model=stage.model)
            return None
        now = time.time()
        u = self.config.utterances
        run = StreamRun(index, stream, now, now, splitter=Splitter(u.false_switch_max_words, u.longest_s))
        run.reader = self.spawn(self.read(run))
        self.spawn(self.charge_periodically(run))
        self.log("stt open", stream=index)
        return run

    async def close_stream(self, finalize: bool) -> None:
        run, self.run = self.run, None
        await self.close_run(run, finalize)

    async def close_run(self, run: StreamRun | None, finalize: bool) -> None:
        if run is None:
            return
        if finalize:
            await self.finalize(run)
        with contextlib.suppress(SttError):
            await run.stream.close()
        if run.reader is not None:
            with contextlib.suppress(asyncio.TimeoutError, asyncio.CancelledError):
                await asyncio.wait_for(asyncio.shield(run.reader), 10)
            run.reader.cancel()
        self.flush_utterances(run, run.splitter.endpoint())
        await self.charge(run, time.time())
        self.log("stt closed", stream=run.index)

    async def finalize(self, run: StreamRun | None) -> None:
        if run is None:
            return
        with contextlib.suppress(SttError):
            await run.stream.send_audio(FINALIZE_SILENCE)
            await run.stream.finalize()
        self.log("stt finalize", stream=run.index, silence_ms=len(FINALIZE_SILENCE) // 32)

    async def read(self, run: StreamRun) -> None:
        try:
            async for event in run.stream.events():
                self.on_event(run, event)
                if event.finished:
                    break
        except SttError as e:
            if self.run is run:
                self.stream_failed(run, e)

    def on_event(self, run: StreamRun, event: SttEvent) -> None:
        self.log("stt", stream=run.index, raw=dict(event.raw))
        if event.words and time.monotonic() - self.last_pulse >= SPEECH_PULSE_S:
            self.last_pulse = time.monotonic()
            self.spawn(self.send({"type": "speech"}))
        finals = [w for w in event.words if w.final]
        done = run.splitter.add(finals) if finals else []
        if event.endpoint or event.finished:
            done += run.splitter.endpoint()
        self.flush_utterances(run, done)
        if event.endpoint and self.run is run and time.time() - run.opened >= ROTATE_AFTER_S:
            self.spawn(self.rotate(run))

    async def rotate(self, run: StreamRun) -> None:
        """Replace a stream nearing Soniox's limit, at a segment end: the new
        one opens while the old one still takes the audio, then the old one
        closes. The new stream's speaker labels start afresh, after a
        "(gap)". If the new one doesn't open, the old one carries on until
        the next segment end."""
        if self.run is not run or self.state != "listening":
            return
        self.log("stt rotate", stream=run.index, open_s=round(time.time() - run.opened))
        new = await self.new_run()
        if new is None:
            return
        if self.run is not run or self.state != "listening":  # paused or dropped meanwhile
            await self.close_run(new, finalize=False)
            return
        self.run = new
        await self.close_run(run, finalize=False)
        self.heard.append(Marker("gap", time.time()))

    def flush_utterances(self, run: StreamRun, utterances: list[Utterance]) -> None:
        for utterance in utterances:
            self.utterance_count += 1
            heard = Heard(f"U{self.utterance_count}", run.index, utterance, run.opened + utterance.end_ms / 1000)
            self.heard.append(heard)
            self.log("utterance", **heard.event())
            self.sessions.on_utterance(self, heard)

    def stream_failed(self, run: StreamRun, error: SttError) -> None:
        """Speech-to-text dropped: reopen it with backoff. Audio still reaches the recording."""
        if self.run is not run:
            return
        log.warning("session %s: speech-to-text stream %d failed: %s", self.id, run.index, error)
        self.log("stt failed", stream=run.index, kind=error.kind, detail=error.detail)
        stage = self.config.stages.speech_to_text
        self.failure("speech-to-text", error.kind, provider=stage.provider, model=stage.model)
        self.health.begin("stt-reopening")
        self.run = None
        self.flush_utterances(run, run.splitter.endpoint())
        self.spawn(self.charge(run, time.time()))
        self.heard.append(Marker("gap", time.time()))
        self.spawn(self.reopen(0))

    async def reopen(self, attempt: int) -> None:
        await asyncio.sleep(REOPEN_BACKOFF_S[min(attempt, len(REOPEN_BACKOFF_S) - 1)])
        if self.state == "listening" and self.run is None:
            await self.open_stream(attempt)

    # --- Cost ------------------------------------------------------------------------

    async def charge_periodically(self, run: StreamRun) -> None:
        while True:
            await asyncio.sleep(COST_EVERY_S)
            await self.charge(run, time.time())

    async def charge(self, run: StreamRun, until: float) -> None:
        seconds, run.charged_until = until - run.charged_until, until
        if seconds <= 0:
            return
        stage = self.config.stages.speech_to_text
        usd = costs_module.stream_cost(self.config, stage, seconds)
        self.cost_usd += usd
        try:
            await self.sessions.costs.charge("speech-to-text", stage.provider, stage.model, usd)
        except Exception:  # noqa: BLE001 - a cost that can't be written is logged, never fatal
            log.exception("session %s: couldn't write a charge of $%.6f", self.id, usd)


class Sessions:
    """Every live session, and the summaries of those that ended lately."""

    def __init__(self, config: Config, prompts: dict[str, Prompt], store: Store, stt: SpeechToText,
                 commit: str = "unknown") -> None:
        self.config, self.prompts, self.store, self.stt, self.commit = config, prompts, store, stt, commit
        self.costs = Costs(store, config)
        self.failures = FailureLog(store)
        self.live: dict[str, Session] = {}
        self.ended: dict[str, Summary] = {}
        self.started: dict[str, str] = {}  # the page's start_id → session id
        # Step 3 plugs in the decision call and location, step 4 the
        # candidates' checks, step 6 the settle call (their `install`).
        self.decider: Any = None
        self.locator: Any = None
        self.checker: Any = None
        self.settler: Any = None
        self.states: Any = None  # the saved sessions, step 7 (`carl.resume`)

    def build_info(self) -> dict[str, Any]:
        """What each recording stores at its start: the config, the prompts and the commit."""
        return {
            "commit": self.commit,
            "config": {"version": self.config.version, "text": self.config.text},
            "prompts": {p.name: {"version": p.version, "text": p.text} for p in self.prompts.values()},
        }

    async def start(self, link: Link, message: dict[str, Any]) -> Session:
        disclosure = message.get("disclosure")
        disclosed = isinstance(disclosure, dict) and bool(disclosure.get("text")) and bool(disclosure.get("confirmed_at"))
        record = bool(message.get("record"))
        if record and not disclosed:
            log.warning("a recording session was asked for without a confirmed disclosure: not recording")
            record = False
        start_id = str(message.get("start_id") or "")[:100]
        session = Session(self, new_session_id(), record=record, timezone=str(message.get("timezone") or "UTC"),
                          start_id=start_id)
        self.live[session.id] = session
        if start_id:
            self.started[start_id] = session.id
        await session.attach(link)
        header = {k: message.get(k) for k in ("disclosure", "mic", "timezone", "location")}
        await session.begin(header)
        log.info("session %s started, %s", session.id, "recording" if session.record else "not recording")
        return session

    def get(self, session_id: str) -> Session | None:
        return self.live.get(session_id)

    def started_as(self, message: dict[str, Any]) -> str | None:
        """The session a resent `start` already started, by its start_id."""
        start_id = str(message.get("start_id") or "")[:100]
        return self.started.get(start_id) if start_id else None

    def finished(self, session: Session) -> None:
        self.live.pop(session.id, None)
        if session.summary is not None:
            self.ended[session.id] = session.summary

    async def stop_recording(self, session_id: str) -> bool:
        """Apply a stop whenever it arrives, even after the session ended. False for a bad id."""
        if not SESSION_ID.fullmatch(session_id):
            return False
        if (session := self.live.get(session_id)) is not None:
            await session.stop_recording()
            return True
        deleted = await self.store.delete_prefix(f"recordings/{session_id}/")
        if (summary := self.ended.get(session_id)) is not None and summary.recording == "kept":
            summary.recording = "stopped"
        log.info("recording %s stopped after its session ended: %d objects deleted", session_id, deleted)
        return True

    async def month_eur(self) -> float | None:
        try:
            month = await self.costs.month()
        except Exception:  # noqa: BLE001
            log.exception("couldn't read the month's cost")
            return None
        return round(costs_module.to_eur(self.config, month["usd"]), 2)

    async def month_costs(self) -> dict[str, float | None]:
        try:
            usd = (await self.costs.month())["usd"]
        except Exception:  # noqa: BLE001
            log.exception("couldn't read the month's cost")
            return {"month_usd": None, "month_eur": None}
        return {"month_usd": round(usd, 6), "month_eur": round(costs_module.to_eur(self.config, usd), 2)}

    def on_utterance(self, session: Session, heard: Heard) -> None:
        """Each utterance goes to the decision call and the settle call, each
        its own task. The settle call first waits for the decisions still
        running on earlier utterances. A session being saved at a shutdown
        starts none: its utterances are saved, undecided."""
        if self.decider is None or session.suspended:
            return
        earlier = set(session.deciding)
        decision = session.spawn_check(self.decider.on_utterance(session, heard))
        session.deciding.add(decision)
        decision.add_done_callback(session.deciding.discard)
        if self.settler is not None:
            session.spawn_check(self.settler.on_utterance(session, heard, earlier))

    async def on_location(self, session: Session, message: dict[str, Any]) -> None:
        if self.locator is not None:
            await self.locator.on_message(session, message)

    async def end_all(self, reason: str) -> None:
        for session in list(self.live.values()):
            await session.end(reason)

    async def resume(self) -> None:
        """At startup, before serving: every saved session, waiting for its page."""
        if self.states is not None:
            await self.states.resume_all(self)

    async def shutdown(self) -> None:
        """At a graceful shutdown: save each live session for the next
        instance to resume (or, without saved states, end it), then close
        what is left open."""
        for session in list(self.live.values()):
            if self.states is not None:
                await session.suspend()
            else:
                await session.end("server shutdown")
        await self.close()

    async def close(self) -> None:
        """At shutdown, once every session has ended: close what the checks
        hold open, and write out the failure log."""
        if self.checker is not None:
            await self.checker.close()
        await self.failures.flush()
