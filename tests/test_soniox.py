import asyncio
import json

import aiohttp
import pytest
from aiohttp import web

from carl.config import Stage
from carl.stt import SttError, Word, soniox
from carl.stt.soniox import Soniox

KEY = "test-key"


class FakeSoniox:
    """A local stand-in for Soniox's WebSocket. It keeps every frame it is
    sent, answers an empty frame with `finished` as Soniox does, and a test
    sends everything else through `socket`."""

    def __init__(self) -> None:
        self.url = ""
        self.frames: asyncio.Queue[dict | bytes | str] = asyncio.Queue()
        self.sockets: asyncio.Queue[web.WebSocketResponse] = asyncio.Queue()
        self.refuse_with: int | None = None
        self.finish_on_close = True

    async def handle(self, request: web.Request) -> web.StreamResponse:
        if self.refuse_with:
            return web.Response(status=self.refuse_with)
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        self.sockets.put_nowait(ws)
        async for message in ws:
            if message.type is aiohttp.WSMsgType.TEXT:
                self.frames.put_nowait(json.loads(message.data) if message.data else "")
            else:
                self.frames.put_nowait(message.data)
            if message.data in ("", b"") and self.finish_on_close:
                await ws.send_json({"tokens": [], "final_audio_proc_ms": 0, "total_audio_proc_ms": 0, "finished": True})
                await ws.close()
        return ws

    async def frame(self) -> dict | bytes | str:
        return await asyncio.wait_for(self.frames.get(), 1)


@pytest.fixture
async def fake(aiohttp_server) -> FakeSoniox:
    fake = FakeSoniox()
    app = web.Application()
    app.router.add_get("/transcribe-websocket", fake.handle)
    server = await aiohttp_server(app)
    fake.url = str(server.make_url("/transcribe-websocket"))
    return fake


@pytest.fixture
async def opened(fake, config):
    """An open stream, the fake's side of its socket, and its config frame."""
    stream = await Soniox(config.stages.speech_to_text, KEY, url=fake.url).open(["fi", "en"])
    ws = await asyncio.wait_for(fake.sockets.get(), 1)
    first = await fake.frame()
    yield stream, ws, first
    await stream.release()


def tok(text: str, start_ms: int = 0, final: bool = True, speaker: str = "1", language: str = "en") -> dict:
    return {"text": text, "start_ms": start_ms, "end_ms": start_ms + 100, "confidence": 0.9,
            "is_final": final, "speaker": speaker, "language": language}


def mark(text: str) -> dict:
    return {"text": text, "is_final": True}


def response(*tokens: dict) -> dict:
    return {"tokens": list(tokens), "final_audio_proc_ms": 0, "total_audio_proc_ms": 0}


async def next_event(events):
    return await asyncio.wait_for(anext(events), 1)


def texts(words: tuple[Word, ...], final: bool) -> list[str]:
    return [w.text for w in words if w.final is final]


# --- Opening and sending ------------------------------------------------------------------


async def test_the_config_frame_starts_the_stream(opened):
    _, _, first = opened
    assert first == {
        "api_key": KEY,
        "model": "stt-rt-v5",
        "audio_format": "pcm_s16le",
        "sample_rate": 16000,
        "num_channels": 1,
        "language_hints": ["fi", "en"],
        "enable_speaker_diarization": True,
        "enable_language_identification": True,
        "enable_endpoint_detection": True,
        "max_endpoint_delay_ms": 1500,
    }


async def test_language_hints_default_to_the_streams_languages(fake):
    stream = await Soniox(Stage("soniox", "stt-rt-v5", {}), KEY, url=fake.url).open(["en"])
    first = await fake.frame()
    assert first["language_hints"] == ["en"]
    assert "enable_endpoint_detection" not in first
    await stream.release()


async def test_audio_passes_on_unchanged(opened, fake):
    stream, _, _ = opened
    chunk = bytes(range(256)) * 12
    await stream.send_audio(chunk)
    await stream.send_audio(b"")  # an empty frame would end the stream, so none is sent
    await stream.keepalive()
    assert await fake.frame() == chunk
    assert await fake.frame() == {"type": "keepalive"}


async def test_finalize_is_a_control_frame(opened, fake):
    stream, _, _ = opened
    await stream.finalize()
    assert await fake.frame() == {"type": "finalize"}


# --- Tokens into words ---------------------------------------------------------------------


async def test_tokens_join_into_words(opened):
    stream, ws, _ = opened
    events = stream.events()
    await ws.send_json(response(tok("Hel", 0), tok("lo", 100), tok(" world", 300), tok(",", 400),
                                tok(" how", 600, False), tok(" are", 800, False, language="fi")))
    event = await next_event(events)
    assert texts(event.words, True) == ["Hello"]
    assert texts(event.words, False) == ["world,", "how", "are"]
    assert event.words[0] == Word("Hello", 0, 200, "1", "en", True)
    assert event.words[-1].language == "fi"
    assert not event.endpoint and not event.finished
    assert event.raw["tokens"][0]["text"] == "Hel"

    await ws.send_json(response(tok(" how", 600), tok(" are", 800), tok(" you", 1000, speaker="2"), tok("?", 1100, speaker="2"),
                                mark("<end>")))
    event = await next_event(events)
    assert texts(event.words, True) == ["world,", "how", "are", "you?"]
    assert texts(event.words, False) == []
    assert event.endpoint
    you = event.words[-1]
    assert (you.speaker, you.start_ms, you.end_ms) == ("2", 1000, 1200)


async def test_a_word_split_across_responses_comes_out_once_and_whole(opened):
    stream, ws, _ = opened
    events = stream.events()
    finals: list[str] = []
    script = [
        response(tok("Hel", 0), tok("sin", 100, False), tok("ki", 200, False)),
        response(tok("sin", 100), tok("ki", 200, False)),
        response(),
        response(tok("ki", 200), tok(" on", 400, False)),
        response(tok(" on", 400), tok(" iso", 600), tok(".", 700), mark("<end>")),
    ]
    interims = []
    for message in script:
        await ws.send_json(message)
        event = await next_event(events)
        finals += texts(event.words, True)
        interims.append(texts(event.words, False))
    assert finals == ["Helsinki", "on", "iso."]
    # An empty response drops the non-final "ki": the next one brings it back.
    assert interims == [["Helsinki"], ["Helsinki"], ["Helsin"], ["Helsinki", "on"], []]


async def test_spaces_as_their_own_tokens_end_words(opened):
    stream, ws, _ = opened
    events = stream.events()
    await ws.send_json(response(tok("How", 0), tok(" ", 100), tok("are", 200), tok(" ", 300, False), tok("you", 400, False)))
    event = await next_event(events)
    assert texts(event.words, True) == ["How"]
    assert texts(event.words, False) == ["are", "you"]


async def test_a_speaker_label_flipping_inside_a_word_doesnt_split_it(opened):
    # As in the live check: Soniox starts each new word with a space, even
    # at a change of speaker or language, but a label can flip mid-word.
    stream, ws, _ = opened
    events = stream.events()
    await ws.send_json(response(tok(" F", 0, speaker="3"), tok("inn", 100, speaker="3"), tok("ish", 200, speaker="2"),
                                tok(" Hel", 400, speaker="2", language="fi"), tok("sinki", 500, speaker="2", language="fi"),
                                tok(" on", 700, speaker="2", language="fi")))
    event = await next_event(events)
    assert [(w.text, w.speaker, w.language, w.final) for w in event.words] == [
        ("Finnish", "3", "en", True), ("Helsinki", "2", "fi", True), ("on", "2", "fi", False)]


async def test_final_tokens_after_an_endpoint_wait_for_the_next_response(opened):
    stream, ws, _ = opened
    events = stream.events()
    await ws.send_json(response(tok("Yes", 0), tok(".", 100), mark("<end>"), tok(" Next", 900), tok(" one", 1000)))
    event = await next_event(events)
    assert event.endpoint
    assert texts(event.words, True) == ["Yes."]
    assert texts(event.words, False) == ["Next", "one"]
    await ws.send_json(response(tok(" please", 1200, False)))
    event = await next_event(events)
    assert not event.endpoint
    assert texts(event.words, True) == ["Next"]
    assert texts(event.words, False) == ["one", "please"]


async def test_finalize_ends_the_segment(opened, fake):
    stream, ws, _ = opened
    events = stream.events()
    await ws.send_json(response(tok("Kah", 0), tok("vi", 100, False)))
    assert texts((await next_event(events)).words, False) == ["Kahvi"]
    await stream.finalize()
    assert await fake.frame() == {"type": "finalize"}
    await ws.send_json(response(tok("vi", 100), tok("a", 200), mark("<fin>")))
    event = await next_event(events)
    assert event.endpoint
    assert texts(event.words, True) == ["Kahvia"]
    assert texts(event.words, False) == []


async def test_close_ends_with_finished(opened, fake):
    stream, ws, _ = opened
    events = stream.events()
    await ws.send_json(response(tok("Moi", 0)))
    assert texts((await next_event(events)).words, False) == ["Moi"]
    await stream.close()
    assert await fake.frame() == ""
    event = await next_event(events)
    assert event.finished
    assert texts(event.words, True) == ["Moi"]
    with pytest.raises(StopAsyncIteration):
        await next_event(events)
    with pytest.raises(SttError) as e:
        await stream.send_audio(b"\0\0")
    assert e.value.kind == "unavailable"


# --- Errors -------------------------------------------------------------------------------


@pytest.mark.parametrize("code, error_type, kind", [
    (429, "limit_exceeded", "rate-limited"),
    (402, "organization_balance_exhausted", "rate-limited"),
    (408, "request_timeout", "timeout"),
    (503, "service_unavailable", "unavailable"),
    (401, "unauthenticated", "unavailable"),
])
async def test_error_frames_become_typed_errors(opened, code, error_type, kind):
    stream, ws, _ = opened
    events = stream.events()
    await ws.send_json(response(tok("Mitä", 0)))
    await next_event(events)
    frame = {"tokens": [], "error_code": code, "error_type": error_type, "error_message": "Something.",
             "request_id": "r-1"}
    await ws.send_json(frame)
    await ws.close()
    event = await next_event(events)  # the error frame, with the words still held
    assert event.raw == frame
    assert texts(event.words, True) == ["Mitä"]
    with pytest.raises(SttError) as e:
        await next_event(events)
    assert e.value.kind == kind
    assert e.value.detail.startswith(f"{code} {error_type}: Something.")


@pytest.mark.parametrize("frame", [
    "not json",
    "[1, 2]",
    json.dumps({"tokens": "Hello"}),
    json.dumps(response({"text": "Hello", "is_final": True})),
    json.dumps(response({"text": "Hello", "start_ms": 0, "end_ms": 100})),
    b"\0\1",
], ids=["not json", "not an object", "tokens not a list", "no times", "no is_final", "binary"])
async def test_garbage_is_bad_output(opened, frame):
    stream, ws, _ = opened
    await (ws.send_bytes(frame) if isinstance(frame, bytes) else ws.send_str(frame))
    with pytest.raises(SttError) as e:
        await next_event(stream.events())
    assert e.value.kind == "bad output"


async def test_a_dropped_connection_is_unavailable(opened):
    stream, ws, _ = opened
    await ws.close()
    with pytest.raises(SttError) as e:
        await next_event(stream.events())
    assert e.value.kind == "unavailable"


async def test_no_finished_after_close_is_a_timeout(opened, fake, monkeypatch):
    monkeypatch.setattr(soniox, "CLOSE_TIMEOUT_S", 0.2)
    stream, _, _ = opened
    fake.finish_on_close = False
    await stream.close()
    with pytest.raises(SttError) as e:
        await next_event(stream.events())
    assert e.value.kind == "timeout"


@pytest.mark.parametrize("status, kind", [(429, "rate-limited"), (503, "unavailable")])
async def test_a_refused_connection_is_typed(fake, config, status, kind):
    fake.refuse_with = status
    with pytest.raises(SttError) as e:
        await Soniox(config.stages.speech_to_text, KEY, url=fake.url).open(["fi", "en"])
    assert e.value.kind == kind


async def test_nothing_listening_is_unavailable(config, unused_tcp_port):
    with pytest.raises(SttError) as e:
        await Soniox(config.stages.speech_to_text, KEY, url=f"ws://127.0.0.1:{unused_tcp_port}/").open(["fi"])
    assert e.value.kind == "unavailable"
