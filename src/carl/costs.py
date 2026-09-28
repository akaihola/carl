"""Cost metering (spec section 11).

Costs are stored in USD, as billed, and shown in euros at the config file's
fixed rate, marked "≈". Months are calendar months in Europe/Helsinki time,
and each charge is dated by its own time. `costs/month-<YYYY-MM>.json` holds
the month-to-date total, rewritten by the single server instance in the
background after every charge, so a model call's cost never holds up the
pipeline.

Each session also has a cost summary, `costs/sessions/<id>.json`, kept
indefinitely since it holds no conversation content: its start and
timezone, duration and listening time, and its cost per stage and per
provider, each split into actual and estimated, with the difference between
a provider's own figure and Carl's where the provider gives one
(`SessionCosts`). It is kept current while the session runs and written for
good at End. A stopped recording leaves only its one line there: "recording
stopped and deleted at hh:mm". `costs/last-session.json` holds the latest
ended session's line for the Start screen: its date, length, cost and €/h.
"""

from __future__ import annotations

import asyncio
import copy
import json
import logging
import math
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .config import Config, Stage
from .storage import Store

log = logging.getLogger(__name__)

MONTH_TZ = ZoneInfo("Europe/Helsinki")
LAST_SESSION = "costs/last-session.json"
# A cost per hour means nothing for a session shorter than this.
PER_HOUR_FROM_S = 60.0
# A session's figures keep this many decimals: a decision call costs about $0.00005.
USD_DIGITS = 8


def month_of(when: datetime) -> str:
    """`YYYY-MM` of the Helsinki month `when` falls in. A naive `when` is UTC."""
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    return f"{when.astimezone(MONTH_TZ):%Y-%m}"


def month_key(when: datetime) -> str:
    """`costs/month-YYYY-MM.json` for the Helsinki month `when` falls in."""
    return f"costs/month-{month_of(when)}.json"


def to_eur(config: Config, usd: float) -> float:
    """Euros at the config file's fixed rate, to be shown as ≈€."""
    return usd / config.currency.ecb_usd_per_eur


def session_key(session_id: str) -> str:
    return f"costs/sessions/{session_id}.json"


def local_time(t: float, timezone: str) -> str:
    """`hh:mm` at wall time `t` in `timezone` (UTC when unknown)."""
    try:
        zone = ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, ValueError):
        zone = ZoneInfo("UTC")
    return f"{datetime.fromtimestamp(t, zone):%H:%M}"


def stopped_line(t: float, timezone: str) -> str:
    """The one line a stopped recording leaves in its session's cost summary."""
    return f"recording stopped and deleted at {local_time(t, timezone)}"


def per_hour(config: Config, usd: float, listening_s: float) -> float | None:
    """Euros per listening hour, or None for a session too short for it to mean anything."""
    if listening_s < PER_HOUR_FROM_S:
        return None
    return round(to_eur(config, usd) / (listening_s / 3600), 4)


@dataclass
class SessionCosts:
    """One session's costs: per stage and per provider, each `{"usd",
    "estimated_usd", "charges"}`, and per provider the provider's own
    figure less Carl's, where it gives one."""

    by_stage: dict[str, dict[str, float]] = field(default_factory=dict)
    by_provider: dict[str, dict[str, float]] = field(default_factory=dict)
    provider_difference_usd: dict[str, float] = field(default_factory=dict)

    def add(self, stage: str, provider: str, usd: float, estimated: bool = False,
            own_usd: float | None = None) -> None:
        """A charge of `usd`; `own_usd` is Carl's own figure when `usd` is the provider's."""
        for table, name in ((self.by_stage, stage), (self.by_provider, provider)):
            row = table.setdefault(name, {"usd": 0.0, "estimated_usd": 0.0, "charges": 0})
            row["usd"] += usd
            row["estimated_usd"] += usd if estimated else 0.0
            row["charges"] += 1
        if own_usd is not None and usd != own_usd:
            self.provider_difference_usd[provider] = self.provider_difference_usd.get(provider, 0.0) + usd - own_usd

    @property
    def usd(self) -> float:
        return sum(row["usd"] for row in self.by_stage.values())

    @property
    def estimated_usd(self) -> float:
        return sum(row["estimated_usd"] for row in self.by_stage.values())

    def event(self) -> dict[str, Any]:
        """As saved: every figure rounded to USD_DIGITS decimals."""
        def rounded(table: dict[str, dict[str, float]]) -> dict[str, dict[str, float]]:
            return {k: {"usd": round(r["usd"], USD_DIGITS), "estimated_usd": round(r["estimated_usd"], USD_DIGITS),
                        "charges": int(r["charges"])} for k, r in sorted(table.items())}

        return {"by_stage": rounded(self.by_stage), "by_provider": rounded(self.by_provider),
                "provider_difference_usd": {k: round(v, USD_DIGITS)
                                            for k, v in sorted(self.provider_difference_usd.items())}}

    @classmethod
    def from_event(cls, data: dict[str, Any]) -> SessionCosts:
        return cls({k: dict(v) for k, v in data["by_stage"].items()},
                   {k: dict(v) for k, v in data["by_provider"].items()}, dict(data["provider_difference_usd"]))


@dataclass(frozen=True)
class Charge:
    """A charge waiting to be added to its month's total."""

    when: datetime
    stage: str
    provider: str
    usd: float
    estimated: bool


def stream_cost(config: Config, stage: Stage, seconds: float) -> float:
    """USD for `seconds` of a speech-to-text stream, from the price table."""
    per_hour = config.price(stage).audio_hour
    if per_hour is None:
        raise ValueError(f"no audio_hour price for {stage.provider} {stage.model}")
    return per_hour / 3600 * seconds


class Costs:
    """The month-to-date totals.

    The single server instance owns them: each month is read from the store
    once, then kept here and written back after every charge. `charge` is
    synchronous and never waits for the store: it queues the charge and a
    task adds it and writes its month (`flush`). A month that can't be read
    keeps its charges queued, since the total they add to is unknown; one
    that can't be written goes out with the next write. `flush` writes
    whatever is left, as at shutdown.
    """

    def __init__(self, store: Store, config: Config) -> None:
        self.store, self.config = store, config
        self._months: dict[str, dict[str, Any]] = {}
        self._queued: list[Charge] = []
        self._unwritten: set[str] = set()  # the months whose total is ahead of the store's
        self._lock = asyncio.Lock()
        self._task: asyncio.Task | None = None
        self._last: dict[str, Any] | None = None  # the last session's line, {} when there is none

    def charge(self, stage: str, provider: str, model: str, usd: float, *, estimated: bool = False,
               when: datetime | None = None) -> None:
        """Queue a charge for its month's total (Helsinki month of `when`, now by default)."""
        if not math.isfinite(usd) or usd < 0:
            raise ValueError(f"not a cost: {usd!r}")
        self._queued.append(Charge(when or datetime.now(UTC), stage, provider, usd, estimated))
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        if self._task is None or self._task.done():
            self._task = loop.create_task(self.flush())

    async def flush(self) -> None:
        """Add the queued charges to their months and write each month that
        changed, until nothing more is queued or the store fails. Never raises."""
        async with self._lock:
            while True:
                queued, self._queued = self._queued, []
                added = await self._add(queued)
                written = await self._write()
                if not (added and written and self._queued):
                    return

    async def _add(self, charges: list[Charge]) -> bool:
        """Add `charges` to their months, in order. False when a month can't
        be read: that charge and the rest go back to the queue's front."""
        for i, c in enumerate(charges):
            try:
                total = await self._load(c.when)
            except Exception:  # noqa: BLE001 - kept queued for the next flush
                log.warning("reading %s failed; %d charges wait", month_key(c.when), len(charges) - i, exc_info=True)
                self._queued[:0] = charges[i:]
                return False
            total["usd"] += c.usd
            if c.estimated:
                total["estimated_usd"] += c.usd
            total["by_stage"][c.stage] = total["by_stage"].get(c.stage, 0.0) + c.usd
            total["by_provider"][c.provider] = total["by_provider"].get(c.provider, 0.0) + c.usd
            total["charges"] += 1
            total["updated"] = datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
            self._unwritten.add(month_key(c.when))
        return True

    async def _write(self) -> bool:
        """Write each month whose total is ahead of the store's. False when a write failed."""
        written = True
        for key in sorted(self._unwritten):
            try:
                await self.store.put(key, json.dumps(self._months[key], indent=2).encode())
            except Exception:  # noqa: BLE001 - written with the next charge, or at shutdown
                log.warning("writing %s failed; the charges go out with the next write", key, exc_info=True)
                written = False
            else:
                self._unwritten.discard(key)
        return written

    async def write_session(self, summary: dict[str, Any]) -> None:
        """Write a session's cost summary. Never raises: it is written again at the next chance."""
        try:
            await self.store.put(session_key(summary["session"]), json.dumps(summary, indent=2).encode())
        except Exception:  # noqa: BLE001
            log.warning("couldn't write the cost summary of %s", summary["session"], exc_info=True)

    async def session(self, session_id: str) -> dict[str, Any] | None:
        data = await self.store.get(session_key(session_id))
        return json.loads(data) if data is not None else None

    async def recording_stopped(self, session_id: str, when: float) -> None:
        """A recording stopped after its session ended: its summary gets the one line."""
        try:
            summary = await self.session(session_id)
            if summary is None:
                return
            summary["recording"] = "stopped"
            summary["recording_stopped"] = stopped_line(when, summary.get("timezone") or "UTC")
            await self.write_session(summary)
        except Exception:  # noqa: BLE001
            log.warning("couldn't mark the recording of %s stopped in its cost summary", session_id, exc_info=True)

    async def set_last_session(self, summary: dict[str, Any]) -> None:
        """The Start screen's last-session line, from an ended session's summary."""
        last = {
            "session": summary["session"], "started": summary["started"], "timezone": summary["timezone"],
            "listening_s": summary["listening_s"], "cost_usd": summary["usd"],
            "cost_eur": round(to_eur(self.config, summary["usd"]), 4),
            "eur_per_hour": per_hour(self.config, summary["usd"], summary["listening_s"]),
        }
        self._last = last
        try:
            await self.store.put(LAST_SESSION, json.dumps(last, indent=2).encode())
        except Exception:  # noqa: BLE001
            log.warning("couldn't write the last session's line", exc_info=True)

    async def last_session(self) -> dict[str, Any] | None:
        """The last ended session's line for `hello`: started, timezone,
        listening_s, cost_eur and eur_per_hour; None before the first."""
        if self._last is None:
            data = await self.store.get(LAST_SESSION)
            self._last = json.loads(data) if data is not None else {}
        if not self._last:
            return None
        return {k: self._last.get(k) for k in ("started", "timezone", "listening_s", "cost_eur", "eur_per_hour")}

    async def month(self, when: datetime | None = None) -> dict[str, Any]:
        """The month-to-date object: {"month", "usd", "estimated_usd", "by_stage": {stage: usd},
        "by_provider": {provider: usd}, "charges", "updated"}, all zero before the first charge.
        Every charge queued so far is in it. A failed read raises."""
        await self.flush()
        async with self._lock:
            return copy.deepcopy(await self._load(when or datetime.now(UTC)))

    async def _load(self, when: datetime) -> dict[str, Any]:
        key = month_key(when)
        if key not in self._months:
            data = await self.store.get(key)
            self._months[key] = json.loads(data) if data is not None else {
                "month": month_of(when), "usd": 0.0, "estimated_usd": 0.0,
                "by_stage": {}, "by_provider": {}, "charges": 0, "updated": None,
            }
        return self._months[key]
