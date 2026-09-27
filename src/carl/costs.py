"""Cost metering (spec section 11).

Costs are stored in USD, as billed, and shown in euros at the config file's
fixed rate, marked "≈". Months are calendar months in Europe/Helsinki time,
and each charge is dated by its own time. `costs/month-<YYYY-MM>.json` holds
the month-to-date total, rewritten by the single server instance on every
charge.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from .config import Config, Stage
from .storage import Store

MONTH_TZ = ZoneInfo("Europe/Helsinki")


def month_key(when: datetime) -> str:
    """`costs/month-YYYY-MM.json` for the Helsinki month `when` falls in."""
    raise NotImplementedError


def to_eur(config: Config, usd: float) -> float:
    raise NotImplementedError


def stream_cost(config: Config, stage: Stage, seconds: float) -> float:
    """USD for `seconds` of a speech-to-text stream, from the price table."""
    raise NotImplementedError


class Costs:
    def __init__(self, store: Store, config: Config) -> None:
        raise NotImplementedError

    async def charge(self, stage: str, provider: str, model: str, usd: float, *, estimated: bool = False,
                     when: datetime | None = None) -> None:
        """Add a charge to its month's total (Helsinki month of `when`, now by default)."""
        raise NotImplementedError

    async def month(self, when: datetime | None = None) -> dict[str, Any]:
        """The month-to-date object: {"month", "usd", "estimated_usd", "by_stage": {stage: usd}, "updated"}."""
        raise NotImplementedError
