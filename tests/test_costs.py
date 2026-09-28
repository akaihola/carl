import asyncio
import json
import logging
from datetime import UTC, datetime, timedelta, timezone

import pytest

from carl.costs import Costs, month_key, month_of, stream_cost, to_eur
from carl.session import Sessions
from carl.storage import MemoryStore

from .conftest import GatedStore

SEPT = datetime(2026, 9, 15, 12, tzinfo=UTC)


class YieldingStore(MemoryStore):
    """Gives other tasks a turn inside every read and write."""

    async def get(self, key):
        await asyncio.sleep(0)
        return await super().get(key)

    async def put(self, key, data):
        await asyncio.sleep(0)
        await super().put(key, data)


class FailingStore(MemoryStore):
    def __init__(self, puts: int = 0, gets: int = 0) -> None:
        super().__init__()
        self.puts, self.gets = puts, gets

    async def get(self, key):
        if self.gets > 0:
            self.gets -= 1
            raise ConnectionError("the bucket is away")
        return await super().get(key)

    async def put(self, key, data):
        if self.puts > 0:
            self.puts -= 1
            raise ConnectionError("the bucket is away")
        await super().put(key, data)


def stored(store: MemoryStore, key: str) -> dict:
    return json.loads(store.objects[key])


def test_the_month_is_helsinkis():
    # Summer time: Helsinki is UTC+3, so October starts at 21:00 UTC on 30 September.
    assert month_key(datetime(2026, 9, 30, 20, 59, 59, tzinfo=UTC)) == "costs/month-2026-09.json"
    assert month_key(datetime(2026, 9, 30, 21, 0, tzinfo=UTC)) == "costs/month-2026-10.json"
    assert month_key(datetime(2026, 9, 30, 23, 59, tzinfo=UTC)) == "costs/month-2026-10.json"
    # Winter time: UTC+2, and the year turns too.
    assert month_key(datetime(2026, 12, 31, 21, 59, tzinfo=UTC)) == "costs/month-2026-12.json"
    assert month_key(datetime(2026, 12, 31, 22, 0, tzinfo=UTC)) == "costs/month-2027-01.json"
    # A naive time is UTC; an aware one in any zone gives the same month.
    assert month_key(datetime(2026, 9, 30, 21, 30)) == "costs/month-2026-10.json"
    new_york = timezone(timedelta(hours=-4))
    assert month_key(datetime(2026, 9, 30, 17, 30, tzinfo=new_york)) == "costs/month-2026-10.json"


def test_stream_cost_comes_from_the_price_table(config):
    stt = config.stages.speech_to_text
    assert config.price(stt).audio_hour == 0.12
    assert stream_cost(config, stt, 3600) == pytest.approx(0.12)
    assert stream_cost(config, stt, 90 * 60) == pytest.approx(0.18)
    assert stream_cost(config, stt, 10) == pytest.approx(0.12 / 360)
    assert stream_cost(config, stt, 0) == 0
    with pytest.raises(ValueError, match="no audio_hour price"):
        stream_cost(config, config.stages.decision, 60)


def test_euros_at_the_config_rate(config):
    assert config.currency.ecb_usd_per_eur == 1.1403  # US dollars per euro
    assert to_eur(config, 1.1403) == pytest.approx(1.0)
    assert to_eur(config, 0.18) == pytest.approx(0.18 / 1.1403)
    assert to_eur(config, 10) < 10
    assert to_eur(config, 0) == 0


async def test_a_month_with_no_charges_is_zero(config):
    costs = Costs(MemoryStore(), config)
    assert await costs.month(SEPT) == {
        "month": "2026-09", "usd": 0.0, "estimated_usd": 0.0, "by_stage": {}, "by_provider": {},
        "charges": 0, "updated": None,
    }


async def test_charges_add_up_by_stage_and_provider(config):
    store = MemoryStore()
    costs = Costs(store, config)
    stt = config.stages.speech_to_text
    usd = stream_cost(config, stt, 1800)
    costs.charge("speech-to-text", stt.provider, stt.model, usd, when=SEPT)
    costs.charge("decision", "openai", "gpt-6-luna", 0.0004, when=SEPT)
    costs.charge("fact-finding", "openai", "gpt-6-luna", 0.012, when=SEPT)
    costs.charge("fact-finding", "perplexity", "google/gemini-3.8-flash", 0.02, estimated=True, when=SEPT)
    costs.charge("fact-checking", "openrouter", "typesafe/jev-1.13", 0.0, when=SEPT)
    month = await costs.month(SEPT)
    assert month["month"] == "2026-09"
    assert month["usd"] == pytest.approx(0.06 + 0.0004 + 0.012 + 0.02)
    assert month["estimated_usd"] == pytest.approx(0.02)
    assert month["by_stage"] == pytest.approx(
        {"speech-to-text": 0.06, "decision": 0.0004, "fact-finding": 0.032, "fact-checking": 0.0})
    assert month["by_provider"] == pytest.approx(
        {"soniox": 0.06, "openai": 0.0124, "perplexity": 0.02, "openrouter": 0.0})
    assert month["charges"] == 5
    assert datetime.fromisoformat(month["updated"]) > SEPT
    assert stored(store, "costs/month-2026-09.json") == month
    assert to_eur(config, month["usd"]) == pytest.approx(0.0924 / 1.1403)


async def test_a_session_across_the_month_change_splits_its_cost(config):
    store = MemoryStore()
    costs = Costs(store, config)
    before = datetime(2026, 9, 30, 20, 59, tzinfo=UTC)  # 23:59 in Helsinki
    after = datetime(2026, 9, 30, 21, 1, tzinfo=UTC)  # 00:01 on 1 October
    costs.charge("speech-to-text", "soniox", "stt-rt-v5", 0.01, when=before)
    costs.charge("speech-to-text", "soniox", "stt-rt-v5", 0.03, when=after)
    costs.charge("decision", "openai", "gpt-6-luna", 0.001, estimated=True, when=after)
    await costs.flush()
    assert sorted(store.objects) == ["costs/month-2026-09.json", "costs/month-2026-10.json"]
    september, october = await costs.month(before), await costs.month(after)
    assert (september["month"], september["usd"], september["charges"]) == ("2026-09", 0.01, 1)
    assert (october["month"], october["usd"], october["charges"]) == ("2026-10", pytest.approx(0.031), 2)
    assert (september["estimated_usd"], october["estimated_usd"]) == (0.0, 0.001)


async def test_totals_carry_on_after_a_restart(config):
    store = MemoryStore()
    first = Costs(store, config)
    first.charge("decision", "openai", "gpt-6-luna", 0.25, when=SEPT)
    await first.flush()
    costs = Costs(store, config)
    assert (await costs.month(SEPT))["usd"] == 0.25
    costs.charge("decision", "openai", "gpt-6-luna", 0.5, when=SEPT)
    await costs.flush()
    assert stored(store, "costs/month-2026-09.json")["usd"] == 0.75
    assert stored(store, "costs/month-2026-09.json")["charges"] == 2


async def test_a_charge_never_waits_for_the_store(config):
    store = GatedStore()
    costs = Costs(store, config)
    costs.charge("decision", "openai", "gpt-6-luna", 0.1, when=SEPT)
    await asyncio.sleep(0.01)
    assert store.waiting == 1  # the first charge's write hangs…
    costs.charge("fact-checking", "openrouter", "typesafe/jev-1.13", 0.2, when=SEPT)  # …and this one is queued
    assert store.objects == {}
    store.gate.set()
    await costs.flush()
    assert store.waiting == 0
    month = stored(store, "costs/month-2026-09.json")
    assert (month["usd"], month["charges"]) == (pytest.approx(0.3), 2)
    assert month["by_stage"] == {"decision": 0.1, "fact-checking": 0.2}


async def test_charges_made_during_a_write_all_count(config):
    store = YieldingStore()
    costs = Costs(store, config)
    for _ in range(50):
        costs.charge("decision", "openai", "gpt-6-luna", 0.001, when=SEPT)
        await asyncio.sleep(0)  # the write task runs between charges
    month = await costs.month(SEPT)
    assert month["charges"] == 50
    assert month["usd"] == pytest.approx(0.05)
    assert stored(store, "costs/month-2026-09.json") == month


async def test_a_failed_write_keeps_the_charge(config, caplog):
    store = FailingStore(puts=1)
    costs = Costs(store, config)
    costs.charge("decision", "openai", "gpt-6-luna", 0.1, when=SEPT)
    with caplog.at_level(logging.WARNING, "carl.costs"):
        await costs.flush()
    assert store.objects == {}
    assert "costs/month-2026-09.json failed" in caplog.text
    costs.charge("decision", "openai", "gpt-6-luna", 0.2, when=SEPT)
    await costs.flush()
    assert stored(store, "costs/month-2026-09.json")["usd"] == pytest.approx(0.3)


async def test_a_failed_write_goes_out_at_the_next_flush_with_no_new_charge(config):
    store = FailingStore(puts=1)
    costs = Costs(store, config)
    costs.charge("decision", "openai", "gpt-6-luna", 0.1, when=SEPT)
    await costs.flush()
    assert store.objects == {}
    await costs.flush()  # as at shutdown
    assert stored(store, "costs/month-2026-09.json")["usd"] == 0.1


async def test_a_failed_read_keeps_the_charges_queued_and_overwrites_nothing(config, caplog):
    store = FailingStore(gets=1)
    await MemoryStore.put(store, "costs/month-2026-09.json", json.dumps({
        "month": "2026-09", "usd": 5.0, "estimated_usd": 0.0, "by_stage": {"decision": 5.0},
        "by_provider": {"openai": 5.0}, "charges": 100, "updated": "2026-09-14T10:00:00.000Z"}).encode())
    costs = Costs(store, config)
    costs.charge("decision", "openai", "gpt-6-luna", 0.1, when=SEPT)
    costs.charge("decision", "openai", "gpt-6-luna", 0.1, when=SEPT)
    with caplog.at_level(logging.WARNING, "carl.costs"):
        await costs.flush()
    assert "reading costs/month-2026-09.json failed; 2 charges wait" in caplog.text
    assert stored(store, "costs/month-2026-09.json")["usd"] == 5.0
    costs.charge("decision", "openai", "gpt-6-luna", 0.1, when=SEPT)
    await costs.flush()
    assert stored(store, "costs/month-2026-09.json")["usd"] == pytest.approx(5.3)
    assert stored(store, "costs/month-2026-09.json")["charges"] == 103


async def test_shutdown_writes_what_the_background_couldnt(config, stt):
    store = FailingStore(puts=1)
    sessions = Sessions(config, {}, store, stt, "test")
    sessions.costs.charge("decision", "openai", "gpt-6-luna", 0.1, when=SEPT)
    await asyncio.sleep(0.01)  # the background write fails
    assert store.objects == {}
    await sessions.close()
    assert stored(store, "costs/month-2026-09.json")["usd"] == 0.1


async def test_the_month_raises_when_it_cant_be_read(config):
    costs = Costs(FailingStore(gets=1), config)
    with pytest.raises(ConnectionError):
        await costs.month(SEPT)
    assert (await costs.month(SEPT))["usd"] == 0.0


@pytest.mark.parametrize("usd", [float("nan"), float("inf"), -0.01])
async def test_a_charge_must_be_a_cost(config, usd):
    costs = Costs(MemoryStore(), config)
    with pytest.raises(ValueError):
        costs.charge("decision", "openai", "gpt-6-luna", usd, when=SEPT)
    assert (await costs.month(SEPT))["charges"] == 0


async def test_the_month_object_is_a_copy(config):
    costs = Costs(MemoryStore(), config)
    costs.charge("decision", "openai", "gpt-6-luna", 0.1, when=SEPT)
    month = await costs.month(SEPT)
    month["usd"] = 99.0
    month["by_stage"]["decision"] = 99.0
    assert (await costs.month(SEPT))["usd"] == 0.1
    assert (await costs.month(SEPT))["by_stage"] == {"decision": 0.1}


async def test_the_default_month_is_now(config):
    costs = Costs(MemoryStore(), config)
    costs.charge("decision", "openai", "gpt-6-luna", 0.1)
    assert (await costs.month())["usd"] == 0.1
    assert (await costs.month())["month"] == month_of(datetime.now(UTC))
