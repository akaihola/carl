"""A recording session's recording (spec section 9, What a recording keeps).

Everything goes under `recordings/<id>/` in the store while the session
runs, not at End:

- `audio/<n>.pcm`: raw 16 kHz 16-bit mono PCM exactly as sent to
  speech-to-text, in objects of about one minute. An object ends early at a
  break in the audio (Pause, a dropped connection), so each holds one
  unbroken stretch; an `audio` event in the log says where it starts.
- `events/<n>.jsonl`: the event log, one JSON object per line with
  `time` (ISO 8601 UTC) and `event`, written as a new part about every 10 s,
  so a crash loses at most one audio object's tail and a few seconds of log.
"""

from __future__ import annotations

from typing import Any

from .storage import Store

AUDIO_OBJECT_BYTES = 16000 * 2 * 60  # about one minute
FLUSH_S = 10.0


class Recorder:
    def __init__(self, store: Store, session_id: str) -> None:
        raise NotImplementedError

    @property
    def prefix(self) -> str:
        """`recordings/<id>/`."""
        raise NotImplementedError

    @property
    def active(self) -> bool:
        """True until `stop_and_delete` or `close`."""
        raise NotImplementedError

    def log(self, event: str, **fields: Any) -> None:
        """Queue an event for the log. Ignored once stopped."""
        raise NotImplementedError

    def audio(self, chunk: bytes) -> None:
        """Queue audio exactly as sent to speech-to-text. Ignored once stopped."""
        raise NotImplementedError

    def audio_break(self) -> None:
        """The audio stops here (Pause, a drop): end the current audio object."""
        raise NotImplementedError

    async def flush(self) -> None:
        """Write the queued events as a new part, and any full or ended audio object."""
        raise NotImplementedError

    async def run(self) -> None:
        """Flush every FLUSH_S until closed or stopped. Run it as a task."""
        raise NotImplementedError

    async def close(self) -> None:
        """Write everything still queued, and stop."""
        raise NotImplementedError

    async def stop_and_delete(self) -> int:
        """The one-way stop: delete all of `recordings/<id>/` at once and keep
        nothing more. Returns how many objects were deleted."""
        raise NotImplementedError
