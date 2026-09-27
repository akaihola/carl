"""Cost metering (spec section 11).

Costs are stored in USD, as billed, and shown in euros at the config file's
fixed rate, marked "≈". Months are calendar months in Europe/Helsinki time,
and each charge is dated by its own time. `costs/month-<YYYY-MM>.json` holds
the month-to-date total, rewritten by the single server instance on every
charge.
"""

from __future__ import annotations

import asyncio
import copy
import json
import logging
import math
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

from .config import Config, Stage
from .storage import Store

log = logging.getLogger(__name__)

MONTH_TZ = ZoneInfo("Europe/Helsinki")


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


def stream_cost(config: Config, stage: Stage, seconds: float) -> float:
    """USD for `seconds` of a speech-to-text stream, from the price table."""
    per_hour = config.price(stage).audio_hour
    if per_hour is None:
        raise ValueError(f"no audio_hour price for {stage.provider} {stage.model}")
    return per_hour / 3600 * seconds


class Costs:
    """The month-to-date totals.

    The single server instance owns them: each month is read from the store
    once, then kept here and written back on every charge. A failed write
    keeps the charge, which goes out with the next one; a failed read raises,
    since the total it would add to is unknown.
    """

    def __init__(self, store: Store, config: Config) -> None:
        self.store, self.config = store, config
        self._months: dict[str, dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    async def charge(self, stage: str, provider: str, model: str, usd: float, *, estimated: bool = False,
                     when: datetime | None = None) -> None:
        """Add a charge to its month's total (Helsinki month of `when`, now by default)."""
        if not math.isfinite(usd) or usd < 0:
            raise ValueError(f"not a cost: {usd!r}")
        when = when or datetime.now(UTC)
        async with self._lock:
            total = await self._load(when)
            total["usd"] += usd
            if estimated:
                total["estimated_usd"] += usd
            total["by_stage"][stage] = total["by_stage"].get(stage, 0.0) + usd
            total["by_provider"][provider] = total["by_provider"].get(provider, 0.0) + usd
            total["charges"] += 1
            total["updated"] = datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
            try:
                await self.store.put(month_key(when), json.dumps(total, indent=2).encode())
            except Exception:
                log.warning("writing %s failed; the charge goes out with the next one", month_key(when), exc_info=True)

    async def month(self, when: datetime | None = None) -> dict[str, Any]:
        """The month-to-date object: {"month", "usd", "estimated_usd", "by_stage": {stage: usd},
        "by_provider": {provider: usd}, "charges", "updated"}, all zero before the first charge."""
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
