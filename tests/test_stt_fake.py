import pytest

from carl.stt import SttError, SttEvent
from carl.stt.fake import FakeSpeechToText, words


async def test_a_fake_stream_plays_its_script_then_what_a_test_adds():
    stt = FakeSpeechToText([SttEvent(words("1", "Hei kaikki"), endpoint=True)])
    stream = await stt.open(["fi", "en"])
    assert stream.languages == ["fi", "en"]
    await stream.send_audio(b"\1\2")
    await stream.keepalive()
    stream.say("2", "Moi vaan", start_ms=1000)
    await stream.finalize()
    await stream.close()
    events = [e async for e in stream.events()]
    assert [[w.text for w in e.words] for e in events] == [["Hei", "kaikki"], ["Moi", "vaan"], [], []]
    assert events[1].words[0].start_ms == 1000
    assert [e.endpoint for e in events] == [True, True, True, True]
    assert events[-1].finished
    assert (bytes(stream.audio), stream.keepalives, stream.finalized, stream.closed) == (b"\1\2", 1, 1, True)
    with pytest.raises(SttError):
        await stream.send_audio(b"\0")


async def test_a_fake_stream_fails_when_told():
    stt = FakeSpeechToText()
    stream = await stt.open(["fi"])
    stream.fail("unavailable", "gone")
    with pytest.raises(SttError) as e:
        [e async for e in stream.events()]
    assert e.value.kind == "unavailable"
    stt.open_error = SttError("rate-limited")
    with pytest.raises(SttError):
        await stt.open(["fi"])
    assert len(stt.streams) == 1
