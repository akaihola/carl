"""Resuming after a restart (spec section 10, Session continuity).

Each live session's state is saved to `sessions/<id>/state.json` as it
changes (`Session.keep_saved`): at once after a change that matters (a
candidate or card changing state, Pause, a recording stop), otherwise at
most every `SAVE_EVERY_S`, and only when something changed. It is deleted
at End; the bucket's 1-day rule on `sessions/` removes any left behind,
since it holds recent conversation.

The state holds what the session needs to carry on, and no more:

- the session's id, its page's start id, when it started, its timezone,
  whether it is listening or paused, whether it records and whether the
  recording was stopped, its listening time and running cost, and its
  speech-to-text stream and utterance counts;
- the recent utterances the decision call's context window can still reach
  (at most `context_utterances`, none older than `context_window_s`), with
  their "(paused)" and "(gap)" markers;
- every candidate: its id, kind, state, probability, restatement, card
  language and utterance, since the decision call lists the whole session's
  candidates;
- every card sent, with its state and times;
- the current place name, never coordinates, and which utterances disputed
  a card.

At every server start, before it serves, each saved session is rebuilt as a
live session waiting for its page (`Sessions.resume`): the reconnect grace
period starts again, and a session whose page doesn't come back is ended as
usual. Its speech-to-text stream opens only when the page rejoins, so no
stream is paid for with nobody there, and the context gets "(gap)", since
labels start afresh. A recording carries on under the same prefix, after
the parts already written. A candidate that was still being checked lost
its check in the restart: it fails (`lost-in-restart`, so a repeat of it is
checked anew). A card that was ready but not yet shown goes to the page
again in the rejoin's `cards`.

At a graceful shutdown (a redeploy or a scale-down), each live session is
saved rather than ended (`Session.suspend`), for the next instance to
resume.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict
from typing import Any

from .costs import SessionCosts
from .decision import Candidate
from .language import CardLanguage
from .location import Place
from .session import Card, Heard, Marker, Session, Sessions, iso_time
from .storage import Store
from .stt import Word
from .utterances import Utterance

log = logging.getLogger(__name__)

VERSION = 1
PREFIX = "sessions/"
# A candidate in these states was being checked: the restart lost its check.
CHECKING = {"finding": "fact-finding", "checking": "fact-checking"}


def key(session_id: str) -> str:
    return f"{PREFIX}{session_id}/state.json"


def heard_state(item: Heard | Marker) -> dict[str, Any]:
    if isinstance(item, Marker):
        return {"marker": item.kind, "time": item.time}
    return {"id": item.id, "stream": item.stream, "time": item.time, "speaker": item.utterance.speaker,
            "words": [asdict(w) for w in item.utterance.words]}


def heard_from(data: dict[str, Any]) -> Heard | Marker:
    if "marker" in data:
        return Marker(data["marker"], data["time"])
    words = tuple(Word(**w) for w in data["words"])
    return Heard(data["id"], data["stream"], Utterance(data["speaker"], words), data["time"])


def recent(session: Session, now: float) -> list[Heard | Marker]:
    """The utterances a later decision call's context window can still reach, with the markers among and after them."""
    s = session.config.decision
    kept: list[Heard | Marker] = []
    count = 0
    for item in reversed(session.heard):
        if isinstance(item, Heard):
            if count == s.context_utterances or now - item.time > s.context_window_s:
                break
            count += 1
        kept.append(item)
    return kept[::-1]


def snapshot(session: Session, now: float | None = None) -> dict[str, Any]:
    """The session's state, as saved. Nothing in it changes unless the session does."""
    now = time.time() if now is None else now
    return {
        "version": VERSION, "session": session.id, "start_id": session.start_id, "started": session.started,
        "timezone": session.timezone, "state": session.state, "record": session.record,
        "recording_stopped": session.recording_stopped,
        "listening_s": session.listening_s, "listening_since": session.listening_since,
        "cost_usd": session.cost_usd, "streams": session.streams, "utterance_count": session.utterance_count,
        "place": None if session.place is None else asdict(session.place),
        "heard": [heard_state(item) for item in recent(session, now)],
        "candidates": [{
            "id": c.id, "kind": c.kind, "state": c.state, "probability": c.probability,
            "restatement": c.restatement, "repeat_of": c.repeat_of, "card_language": c.card_language.event(),
            "heard": heard_state(c.heard),
        } for c in session.candidates],
        "cards": [{
            "id": c.id, "content": c.content, "utterance_time": c.utterance_time, "state": c.state, "sent": c.sent,
            "shown_at": c.shown_at, "shown_received": c.shown_received, "filed_at": c.filed_at,
            "filed_received": c.filed_received, "late": c.late,
        } for c in session.cards.values()],
        "disputing": session.disputing,
        "spend": session.spend.event(), "recording_stopped_at": session.recording_stopped_at,
    }


def restore(sessions: Sessions, data: dict[str, Any], saved_at: float) -> Session:
    """A live session rebuilt from its saved state, not yet carrying on
    (`Session.carry_on`). Its listening time runs up to when it was saved."""
    if data.get("version") != VERSION:
        raise ValueError(f"state version {data.get('version')!r}")
    session = Session(sessions, data["session"], record=data["record"], started=data["started"],
                      state=data["state"], timezone=data["timezone"], start_id=data.get("start_id") or "")
    session.recording_stopped = data["recording_stopped"]
    since = data["listening_since"]
    session.listening_s = data["listening_s"] + (max(0.0, saved_at - since) if since is not None else 0.0)
    session.cost_usd, session.streams = data["cost_usd"], data["streams"]
    session.utterance_count = data["utterance_count"]
    session.place = None if data["place"] is None else Place(**data["place"])
    session.heard = [heard_from(item) for item in data["heard"]]
    by_id = {item.id: item for item in session.heard if isinstance(item, Heard)}
    for c in data["candidates"]:
        heard = by_id.get(c["heard"].get("id")) or heard_from(c["heard"])
        language = c["card_language"]
        session.candidates.append(Candidate(
            c["id"], c["kind"], heard, c["probability"],
            CardLanguage(language["language"], language["rule"], language["window_words"], language["own_words"]),
            restatement=c["restatement"], state=c["state"], repeat_of=c["repeat_of"]))
    candidates = {c.id: c for c in session.candidates}
    for c in data["cards"]:
        session.cards[c["id"]] = Card(
            c["id"], c["content"], c["utterance_time"], candidates.get(c["id"]), c["state"], c["sent"], c["shown_at"],
            c["shown_received"], c["filed_at"], c["filed_received"], c["late"])
    session.disputing = dict(data["disputing"])
    session.spend = SessionCosts.from_event(data["spend"])
    session.recording_stopped_at = data["recording_stopped_at"]
    return session


class SessionStates:
    """The saved sessions in the store: `Sessions.states`."""

    def __init__(self, store: Store) -> None:
        self.store = store
        self.written: dict[str, bytes] = {}  # each session's state as last written

    async def save(self, session: Session, *, force: bool = False) -> None:
        """Write the session's state if it changed since the last write. Never raises."""
        body = json.dumps(snapshot(session), ensure_ascii=False, sort_keys=True, default=str).encode()
        if not force and self.written.get(session.id) == body:
            return
        data = json.dumps({"saved": time.time(), "saved_at": iso_time(time.time()),
                           "state": json.loads(body)}, ensure_ascii=False).encode()
        try:
            await self.store.put(key(session.id), data)
        except Exception:  # noqa: BLE001 - tried again at the next save
            log.warning("session %s: couldn't save its state", session.id, exc_info=True)
            return
        self.written[session.id] = body

    async def delete(self, session_id: str) -> None:
        self.written.pop(session_id, None)
        try:
            await self.store.delete_prefix(f"{PREFIX}{session_id}/")
        except Exception:  # noqa: BLE001 - the bucket's 1-day rule is the backstop
            log.warning("session %s: couldn't delete its state", session_id, exc_info=True)

    async def resume_all(self, sessions: Sessions) -> list[Session]:
        """Every saved session, rebuilt and waiting for its page. A state
        that can't be read is left for the bucket's rule to remove."""
        resumed = []
        for name in await self.store.list(PREFIX):
            if not name.endswith("/state.json"):
                continue
            try:
                saved = json.loads((await self.store.get(name)) or b"null")
                session = restore(sessions, saved["state"], saved["saved"])
            except Exception:  # noqa: BLE001
                log.exception("couldn't resume %s", name)
                continue
            if session.id in sessions.live:
                continue
            sessions.live[session.id] = session
            if session.start_id:
                sessions.started[session.start_id] = session.id
            self.written[session.id] = json.dumps(saved["state"], ensure_ascii=False, sort_keys=True,
                                                  default=str).encode()
            await session.carry_on(saved.get("saved_at"))
            resumed.append(session)
            log.info("session %s resumed after a restart; waiting for its page", session.id)
        return resumed


def install(sessions: Sessions) -> None:
    """Save each session's state, and resume saved ones at startup (`Sessions.states`)."""
    sessions.states = SessionStates(sessions.store)
