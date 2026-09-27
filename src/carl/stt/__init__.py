"""The speech-to-text interface (spec section 3, Stage interfaces).

Provider-neutral: the pipeline sees only these types. An adapter per
provider sits behind `open_stream`, selected by the config file's
`stages.speech_to_text`. Splitting final words into utterances happens in
the pipeline (`carl.utterances`), not in the adapter.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from ..config import Stage

# Raw 16 kHz 16-bit little-endian mono PCM, as the page sends it.
AUDIO_FORMAT = "s16le"
SAMPLE_RATE = 16000


@dataclass(frozen=True)
class Word:
    """One word as speech-to-text heard it.

    Times are milliseconds from the start of the stream. `speaker` is only
    valid within its own stream: every new stream starts fresh labels.
    `language` is the code the provider tagged the word with ("fi", "en");
    an adapter for a one-language-per-stream provider tags every word with
    the stream's language.
    """

    text: str
    start_ms: int
    end_ms: int
    speaker: str
    language: str
    final: bool


@dataclass(frozen=True)
class SttEvent:
    """One message from the provider.

    - `words`: the interim and final words it carried, in order.
    - `endpoint`: the provider marked the end of a segment (speech ended), so
      every final word so far belongs to a finished segment.
    - `finished`: the stream is over; nothing more will come.
    - `raw`: the provider's message as it came, for the recording.
    """

    words: tuple[Word, ...] = ()
    endpoint: bool = False
    finished: bool = False
    raw: Mapping[str, Any] = field(default_factory=dict)


class SttError(Exception):
    """A typed failure: `kind` is timeout, unavailable, rate-limited or bad output."""

    def __init__(self, kind: Literal["timeout", "unavailable", "rate-limited", "bad output"], detail: str = ""):
        super().__init__(f"{kind}: {detail}" if detail else kind)
        self.kind = kind
        self.detail = detail


class SttStream(Protocol):
    """One open stream. Adapters never retry: the pipeline decides."""

    async def send_audio(self, chunk: bytes) -> None:
        """Pass a chunk of raw audio on unchanged."""

    async def keepalive(self) -> None:
        """Keep the stream open while no audio flows (the reconnect grace period)."""

    async def finalize(self) -> None:
        """Make every word heard so far final (Pause), without closing."""

    async def close(self) -> None:
        """End the stream. `events()` then ends with a `finished` event."""

    def events(self) -> AsyncIterator[SttEvent]:
        """The provider's events, until the stream is closed or fails.

        Raises SttError when the provider fails or drops the stream.
        """


class SpeechToText(Protocol):
    async def open(self, languages: list[str]) -> SttStream:
        """Open a stream for raw AUDIO_FORMAT audio at SAMPLE_RATE, mono."""


def make_speech_to_text(stage: Stage, secrets: Mapping[str, str]) -> SpeechToText:
    """The adapter the config file selects, with its key from `secrets`."""
    if stage.provider == "soniox":
        from .soniox import Soniox

        return Soniox(stage, secrets["SONIOX_API_KEY"])
    raise ValueError(f"no speech-to-text adapter for provider {stage.provider!r}")
