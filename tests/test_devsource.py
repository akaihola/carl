import json
import math
import os
import stat
import wave
import zoneinfo
from array import array

import pytest

from carl import devsource, gate
from carl.cli import main
from carl.devsource import DevSendError, dev_send, first_pass, load_pcm, local_origin, local_timezone, resample
from carl.server import create_app
from carl.session import SESSION_ID, Sessions

from .conftest import PASSWORD, ScriptedStt


def write_wav(path, samples, rate=16000, channels=1, width=2):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(width)
        w.setframerate(rate)
        w.writeframes(array("h", samples).tobytes() if width == 2 else bytes(samples))
    return path


def pcm(samples):
    return array("h", samples).tobytes()


def samples(data):
    return list(array("h", data))


# --- The audio ------------------------------------------------------------------------


def test_a_16khz_mono_wav_comes_through_unchanged(tmp_path):
    values = [0, 1, -1, 32767, -32768, 1234]
    assert load_pcm(write_wav(tmp_path / "a.wav", values)) == pcm(values)


def test_stereo_is_downmixed_to_mono(tmp_path):
    frames = [100, 200, -100, -300, 32767, 32767, -32768, -32768, 3, 4]
    assert samples(load_pcm(write_wav(tmp_path / "a.wav", frames, channels=2))) == [150, -200, 32767, -32768, 4]


def test_resampling_interpolates_and_keeps_the_length():
    assert resample([0, 100, 200, 300], 8000) == [0, 50, 100, 150, 200, 250, 300, 300]
    assert resample(list(range(12)), 48000) == [0, 3, 6, 9]
    assert resample([5, 6, 7], 16000) == [5, 6, 7]


def test_a_44_1khz_stereo_wav_becomes_the_same_tone_at_16khz(tmp_path):
    tone = [round(10000 * math.sin(2 * math.pi * 440 * n / 44100)) for n in range(44100 // 2)]
    frames = [s for v in tone for s in (v, v)]
    out = samples(load_pcm(write_wav(tmp_path / "a.wav", frames, rate=44100, channels=2)))
    assert len(out) == 8000
    assert max(abs(v - 10000 * math.sin(2 * math.pi * 440 * n / 16000)) for n, v in enumerate(out)) < 20


def test_other_files_need_ffmpeg(tmp_path, monkeypatch):
    monkeypatch.setattr(devsource.shutil, "which", lambda name: None)
    mp3 = tmp_path / "talk.mp3"
    mp3.write_bytes(b"ID3 not really an mp3")
    for path in (mp3, write_wav(tmp_path / "8bit.wav", [128, 130], width=1)):
        with pytest.raises(DevSendError, match="ffmpeg"):
            load_pcm(path)
    with pytest.raises(DevSendError, match="no such file"):
        load_pcm(tmp_path / "missing.wav")


def test_other_files_go_through_ffmpeg(tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    ffmpeg = bin_dir / "ffmpeg"
    ffmpeg.write_text('#!/bin/sh\necho "$@" > "$(dirname "$0")/args"\nprintf "\\001\\000\\002\\000"\n')
    ffmpeg.chmod(ffmpeg.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    talk = tmp_path / "talk.m4a"
    talk.write_bytes(b"not a wav")
    assert load_pcm(talk) == pcm([1, 2])
    assert f"-i {talk} -f s16le -ac 1 -ar 16000 -" in (bin_dir / "args").read_text()


# --- Local only -----------------------------------------------------------------------


def test_only_a_local_carl():
    assert str(local_origin("http://127.0.0.1:8080/")) == "http://127.0.0.1:8080"
    assert str(local_origin("http://localhost:8080/some/page")) == "http://localhost:8080"
    assert str(local_origin("http://[::1]:9000")) == "http://[::1]:9000"
    for url in ("https://faktat.vempai.men", "http://127.0.0.1.example.com", "http://localhost.example.com",
                "http://192.168.1.10:8080", "localhost:8080", "ftp://localhost", "http://0.0.0.0:8080"):
        with pytest.raises(DevSendError, match="local"):
            local_origin(url)


def test_the_command_refuses_a_remote_carl_before_anything_else(tmp_path, capsys):
    assert main(["dev-send", str(tmp_path / "missing.wav"), "--url", "https://faktat.vempai.men"]) == 2
    assert "only talks to a local Carl" in capsys.readouterr().err


def test_the_command_needs_a_pass_when_there_is_no_local_list(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(devsource, "PASSES_FILE", tmp_path / "none.txt")
    assert main(["dev-send", str(write_wav(tmp_path / "a.wav", [1, 2]))]) == 2
    assert "--pass" in capsys.readouterr().err


def test_the_first_access_pass_from_the_local_list(tmp_path):
    passes = tmp_path / "passes.txt"
    passes.write_text("# Carl's access passes: keep them safe.\n\nowner's phone: fir-st-pass \nlaptop: second\n")
    assert first_pass(passes) == "fir-st-pass"
    assert first_pass(tmp_path / "missing.txt") is None


def test_the_timezone_is_an_iana_name(monkeypatch):
    zoneinfo.ZoneInfo(local_timezone())
    monkeypatch.setenv("TZ", "Europe/Helsinki")
    assert local_timezone() == "Europe/Helsinki"


# --- Against a local Carl -------------------------------------------------------------


class HearingStt(ScriptedStt):
    """Hears a line in each stream as soon as its first audio arrives."""

    async def open(self, languages):
        stream = await super().open(languages)
        send_audio, number = stream.send_audio, len(self.streams)

        async def hear(chunk: bytes) -> None:
            if not stream.audio:
                stream.say("1", f"Tämä tuli tiedostosta, osa {number}.")
            await send_audio(chunk)

        stream.send_audio = hear
        return stream


@pytest.fixture
def stt():
    return HearingStt()


@pytest.fixture
async def carl(aiohttp_server, app_config, passes, store, stt):
    """A local Carl's URL, on a real port."""
    server = await aiohttp_server(create_app(app_config, {}, passes, Sessions(app_config, {}, store, stt, "test")))
    return str(server.make_url("/"))


# 1.25 s of audio that is never silent, so silence the server adds is told apart.
AUDIO = pcm([1000 + n % 500 for n in range(20000)])


def heard(stream) -> bytes:
    """What a stream got from the page: the server may add silence of its own before finalising."""
    audio = bytes(stream.audio)
    end = len(audio.rstrip(b"\0"))
    return audio[: end + end % 2]


async def events(store, session_id):
    lines = []
    for key in await store.list(f"recordings/{session_id}/events/"):
        lines += [json.loads(line) for line in (await store.get(key)).decode().splitlines()]
    return lines


async def test_a_file_reaches_carl_as_the_page_would_send_it(carl, stt, store, capsys):
    ended = await dev_send(AUDIO, "talk.wav", carl, PASSWORD, speed=1000)
    assert SESSION_ID.fullmatch(ended["session"])
    assert ended["summary"]["recording"] == "none"
    assert len(stt.streams) == 1 and heard(stt.streams[0]) == AUDIO and stt.streams[0].closed
    assert await store.list("recordings/") == []
    out = capsys.readouterr().out
    assert f"session {ended['session']} started, not recording" in out
    assert f"session {ended['session']} ended: listening_s" in out
    assert PASSWORD not in out


async def test_a_recorded_run_with_a_pause(carl, stt, store):
    ended = await dev_send(AUDIO, "talk.wav", carl, PASSWORD, record=True, speed=1000, pause_at=0.5)
    session_id = ended["session"]
    assert ended["summary"]["recording"] == "kept"
    # The pause falls at the first 100 ms frame from 0.5 s on.
    assert [heard(s) for s in stt.streams] == [AUDIO[:16000], AUDIO[16000:]]
    assert stt.streams[0].finalized and stt.streams[0].closed
    keys = await store.list(f"recordings/{session_id}/audio/")
    assert len(keys) == 2 and b"".join([await store.get(k) for k in keys]) == AUDIO
    log = await events(store, session_id)
    start = log[0]
    assert start["event"] == "session start"
    assert start["disclosure"]["text"] == "dev-send: talk.wav" and start["disclosure"]["confirmed_at"].endswith("Z")
    assert start["mic"] == {"source": "dev-send", "file": "talk.wav"}
    zoneinfo.ZoneInfo(start["timezone"])
    assert [e["event"] for e in log if e["event"] in ("pause", "resume")] == ["pause", "resume"]
    assert [e["text"] for e in log if e["event"] == "utterance"] == [
        "Tämä tuli tiedostosta, osa 1.", "Tämä tuli tiedostosta, osa 2."]
    assert log[-1]["event"] == "session end" and log[-1]["reason"] == "end"


async def test_heartbeats_keep_a_long_pause_alive(carl, stt, app_config, monkeypatch):
    monkeypatch.setattr(devsource, "PAUSE_S", 2 * app_config.connection.silence_s)
    ended = await dev_send(AUDIO[:6400], "talk.wav", carl, PASSWORD, pause_at=0.1)
    assert ended["summary"]["recording"] == "none"
    assert [heard(s) for s in stt.streams] == [AUDIO[:3200], AUDIO[3200:6400]]


async def test_a_wrong_pass_is_refused_without_showing_it(carl, monkeypatch):
    monkeypatch.setattr(gate, "WRONG_PASS_WAIT_S", 0)
    with pytest.raises(DevSendError, match="didn't take the access pass") as caught:
        await dev_send(AUDIO, "talk.wav", carl, "not-the-right-pass")
    assert "not-the-right-pass" not in str(caught.value)


async def test_no_carl_running_is_a_clear_error(unused_tcp_port):
    with pytest.raises(DevSendError, match="can't reach Carl"):
        await dev_send(AUDIO, "talk.wav", f"http://127.0.0.1:{unused_tcp_port}", PASSWORD)
