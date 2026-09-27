import asyncio
import json
import logging
import re
import threading

import pytest

from carl import recording
from carl.recording import AUDIO_OBJECT_BYTES, Recorder
from carl.storage import MemoryStore

ID = "20260927T180211Z-a1b2c3"
PREFIX = f"recordings/{ID}/"
TIME = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z")
CHUNK = 3200  # 100 ms, as the page sends it


def chunks(count: int, start: int = 0) -> list[bytes]:
    """Distinct 100 ms chunks, so misplaced or lost ones show."""
    return [(i % 65536).to_bytes(2, "little") * (CHUNK // 2) for i in range(start, start + count)]


async def lines(store: MemoryStore) -> list[dict]:
    return [json.loads(line) for key in await store.list(PREFIX + "events/") for line in store.objects[key].splitlines()]


class FailingStore(MemoryStore):
    """Fails the first `failures` puts whose key contains `where`."""

    def __init__(self, failures: int = 1, where: str = "") -> None:
        super().__init__()
        self.failures, self.where = failures, where

    async def put(self, key, data):
        if self.where in key and self.failures > 0:
            self.failures -= 1
            raise ConnectionError("the bucket is away")
        await super().put(key, data)


class SlowStore(MemoryStore):
    """Puts that block in a thread until released and then land, as boto3's do
    even when the coroutine waiting for them is cancelled."""

    def __init__(self) -> None:
        super().__init__()
        self.release = threading.Event()
        self.started = asyncio.Event()

    async def put(self, key, data):
        self.started.set()
        await asyncio.to_thread(self._put, key, data)

    def _put(self, key, data):
        self.release.wait(5)
        self.objects[key] = bytes(data)


async def test_audio_goes_into_objects_of_about_a_minute():
    store = MemoryStore()
    recorder = Recorder(store, ID)
    sent = chunks(1500)  # 2.5 minutes
    for chunk in sent:
        recorder.audio(chunk)
    await recorder.flush()
    assert await store.list(PREFIX) == [PREFIX + "audio/000001.pcm", PREFIX + "audio/000002.pcm",
                                        PREFIX + "events/000001.jsonl"]
    assert store.objects[PREFIX + "audio/000001.pcm"] == b"".join(sent[:600])
    assert store.objects[PREFIX + "audio/000002.pcm"] == b"".join(sent[600:1200])
    audio = await lines(store)
    assert [(e["event"], e["key"], e["bytes"]) for e in audio] == [
        ("audio", "audio/000001.pcm", AUDIO_OBJECT_BYTES), ("audio", "audio/000002.pcm", AUDIO_OBJECT_BYTES)]
    assert all(TIME.fullmatch(e["start"]) and TIME.fullmatch(e["time"]) for e in audio)
    assert audio[0]["start"] <= audio[1]["start"]

    await recorder.close()  # the unfinished half minute
    assert store.objects[PREFIX + "audio/000003.pcm"] == b"".join(sent[1200:])
    assert b"".join(store.objects[k] for k in await store.list(PREFIX + "audio/")) == b"".join(sent)
    last = (await lines(store))[-1]
    assert (last["event"], last["key"], last["bytes"]) == ("audio", "audio/000003.pcm", 300 * CHUNK)


async def test_an_object_never_splits_a_chunk():
    store = MemoryStore()
    recorder = Recorder(store, ID)
    odd = b"\1\0" * 1700  # chunks that don't divide a minute
    for _ in range(AUDIO_OBJECT_BYTES // len(odd) + 1):
        recorder.audio(odd)
    await recorder.flush()
    first = store.objects[PREFIX + "audio/000001.pcm"]
    assert AUDIO_OBJECT_BYTES <= len(first) < AUDIO_OBJECT_BYTES + len(odd)
    assert len(first) % len(odd) == 0


async def test_a_break_ends_the_audio_object_early():
    store = MemoryStore()
    recorder = Recorder(store, ID)
    before, after = chunks(50), chunks(20, start=50)
    for chunk in before:
        recorder.audio(chunk)
    recorder.log("pause")
    recorder.audio_break()
    recorder.audio_break()  # nothing more to end
    recorder.log("resume")
    for chunk in after:
        recorder.audio(chunk)
    await recorder.flush()
    assert await store.list(PREFIX + "audio/") == [PREFIX + "audio/000001.pcm"]  # the second isn't finished
    assert store.objects[PREFIX + "audio/000001.pcm"] == b"".join(before)
    assert [e["event"] for e in await lines(store)] == ["pause", "audio", "resume"]
    await recorder.close()
    assert store.objects[PREFIX + "audio/000002.pcm"] == b"".join(after)
    audio = [e for e in await lines(store) if e["event"] == "audio"]
    assert [(e["key"], e["bytes"]) for e in audio] == [("audio/000001.pcm", 50 * CHUNK), ("audio/000002.pcm", 20 * CHUNK)]


async def test_each_flush_writes_the_queued_events_as_a_new_part():
    store = MemoryStore()
    recorder = Recorder(store, ID)
    recorder.log("session start", mic={"sampleRate": 16000}, disclosure={"text": "Tämä on testi.\nThis is a test."})
    recorder.log("stt", stream=1, raw={"tokens": [{"text": "Einstein", "speaker": "1", "language": "fi"}]})
    await recorder.flush()
    await recorder.flush()  # nothing queued: no empty part
    recorder.log("pause")
    await recorder.flush()
    assert await store.list(PREFIX) == [PREFIX + "events/000001.jsonl", PREFIX + "events/000002.jsonl"]
    first = store.objects[PREFIX + "events/000001.jsonl"].decode()
    assert first.endswith("\n") and len(first.splitlines()) == 2
    assert "Tämä" in first  # kept as UTF-8, not escaped
    start, stt = (json.loads(line) for line in first.splitlines())
    assert list(start) == ["time", "event", "mic", "disclosure"]
    assert TIME.fullmatch(start["time"])
    assert start["event"] == "session start" and start["disclosure"]["text"] == "Tämä on testi.\nThis is a test."
    assert stt["raw"]["tokens"][0]["speaker"] == "1"
    assert [e["event"] for e in await lines(store)] == ["session start", "stt", "pause"]


async def test_a_field_cant_be_called_time():
    with pytest.raises(ValueError):
        Recorder(MemoryStore(), ID).log("card shown", time="18:02")


async def test_close_writes_the_tail_and_ignores_what_comes_after():
    store = MemoryStore()
    recorder = Recorder(store, ID)
    recorder.log("session start")
    recorder.audio(b"\1\0" * 800)
    assert recorder.active
    await recorder.close()
    assert not recorder.active
    recorder.log("too late")
    recorder.audio(b"\2\0" * 800)
    recorder.audio_break()
    await recorder.flush()
    await recorder.close()
    assert await store.list(PREFIX) == [PREFIX + "audio/000001.pcm", PREFIX + "events/000001.jsonl"]
    assert store.objects[PREFIX + "audio/000001.pcm"] == b"\1\0" * 800
    assert [e["event"] for e in await lines(store)] == ["session start", "audio"]


async def test_stop_deletes_everything_and_keeps_nothing_more():
    store = MemoryStore()
    store.objects["recordings/20260927T180211Z-a1b2c3d/events/000001.jsonl"] = b"{}\n"  # another session
    recorder = Recorder(store, ID)
    for chunk in chunks(650):
        recorder.audio(chunk)
    recorder.log("session start")
    await recorder.flush()
    recorder.log("queued, never written")
    written = await store.list(PREFIX)
    assert len(written) == 2
    assert await recorder.stop_and_delete() == 2
    assert not recorder.active
    assert await store.list(PREFIX) == []
    recorder.log("after the stop")
    recorder.audio(b"\1\0" * 1600)
    recorder.audio_break()
    await recorder.flush()
    await recorder.close()
    assert await store.list(PREFIX) == []
    assert await store.list("recordings/") == ["recordings/20260927T180211Z-a1b2c3d/events/000001.jsonl"]
    assert await recorder.stop_and_delete() == 0  # sent again: still fine


async def test_a_stop_after_the_end_deletes_the_recording():
    store = MemoryStore()
    recorder = Recorder(store, ID)
    recorder.log("session start")
    recorder.audio(b"\1\0" * 1600)
    await recorder.close()
    assert await Recorder(store, ID).stop_and_delete() == 2
    assert store.objects == {}


async def test_a_stop_waits_for_a_write_under_way():
    store = SlowStore()
    recorder = Recorder(store, ID)
    recorder.log("session start")
    flush = asyncio.create_task(recorder.flush())
    await store.started.wait()
    stop = asyncio.create_task(recorder.stop_and_delete())
    await asyncio.sleep(0.05)
    assert not stop.done()  # the put could still land
    store.release.set()
    assert await stop == 1
    await flush
    assert store.objects == {}


async def test_a_stop_waits_for_a_write_a_cancelled_flush_left_behind():
    store = SlowStore()
    recorder = Recorder(store, ID)
    recorder.log("session start")
    flush = asyncio.create_task(recorder.flush())
    await store.started.wait()
    flush.cancel()
    with pytest.raises(asyncio.CancelledError):
        await flush
    stop = asyncio.create_task(recorder.stop_and_delete())
    await asyncio.sleep(0.05)
    assert not stop.done()
    store.release.set()
    await stop
    assert store.objects == {}


async def test_a_failed_write_stays_queued_and_goes_out_next_time(caplog):
    store = FailingStore(where="events/")
    recorder = Recorder(store, ID)
    recorder.log("first")
    with caplog.at_level(logging.WARNING, "carl.recording"):
        await recorder.flush()
    assert store.objects == {}
    assert "events/000001.jsonl failed" in caplog.text
    recorder.log("second")
    await recorder.flush()
    recorder.log("third")
    await recorder.flush()
    assert await store.list(PREFIX) == [PREFIX + "events/000001.jsonl", PREFIX + "events/000002.jsonl"]
    assert [e["event"] for e in await lines(store)] == ["first", "second", "third"]


async def test_a_failed_audio_object_keeps_its_place():
    store = FailingStore(where="audio/000001")
    recorder = Recorder(store, ID)
    sent = chunks(700)
    for chunk in sent[:100]:
        recorder.audio(chunk)
    recorder.audio_break()
    for chunk in sent[100:]:
        recorder.audio(chunk)
    await recorder.flush()  # object 1 fails, so object 2 waits behind it
    assert await store.list(PREFIX + "audio/") == []
    await recorder.flush()
    assert await store.list(PREFIX + "audio/") == [PREFIX + "audio/000001.pcm", PREFIX + "audio/000002.pcm"]
    assert store.objects[PREFIX + "audio/000001.pcm"] == b"".join(sent[:100])
    assert store.objects[PREFIX + "audio/000002.pcm"] == b"".join(sent[100:])


async def test_close_tries_again_before_giving_up(monkeypatch, caplog):
    monkeypatch.setattr(recording, "RETRY_S", 0)
    store = FailingStore(failures=2)
    recorder = Recorder(store, ID)
    recorder.log("session end")
    await recorder.close()
    assert [e["event"] for e in await lines(store)] == ["session end"]

    store = FailingStore(failures=100)
    recorder = Recorder(store, ID)
    recorder.log("session end")
    with caplog.at_level(logging.ERROR, "carl.recording"):
        await recorder.close()
    assert "1 events and 0 audio objects could not be written" in caplog.text


async def test_run_flushes_until_closed(monkeypatch):
    monkeypatch.setattr(recording, "FLUSH_S", 0.02)
    store = MemoryStore()
    recorder = Recorder(store, ID)
    task = asyncio.create_task(recorder.run())
    recorder.log("one")
    await asyncio.sleep(0.05)
    assert [e["event"] for e in await lines(store)] == ["one"]
    recorder.log("two")
    await recorder.close()
    await asyncio.wait_for(task, 0.1)  # ends at once
    assert [e["event"] for e in await lines(store)] == ["one", "two"]


async def test_cancelling_run_loses_nothing(monkeypatch):
    monkeypatch.setattr(recording, "FLUSH_S", 0.01)
    store = SlowStore()
    recorder = Recorder(store, ID)
    recorder.log("one")
    task = asyncio.create_task(recorder.run())
    await store.started.wait()  # cancelled in the middle of a write
    task.cancel()
    recorder.log("two")
    store.release.set()
    await recorder.close()
    assert await store.list(PREFIX) == [PREFIX + "events/000001.jsonl"]  # written again, whole
    assert [e["event"] for e in await lines(store)] == ["one", "two"]


def test_a_session_id_is_one_path_segment():
    for bad in ("", "a/b", "../x/"):
        with pytest.raises(ValueError):
            Recorder(MemoryStore(), bad)
    assert Recorder(MemoryStore(), ID).prefix == PREFIX
