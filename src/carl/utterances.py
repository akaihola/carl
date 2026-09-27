"""From final words to utterances (spec section 4, From final segments to utterances).

Pure logic, fed one stream's final words in order. An utterance is one
speaker's run of final words:

- a segment is split wherever the speaker label changes;
- a run of `false_switch_max_words` words or fewer between two runs by the
  same speaker is a false switch, merged into them;
- an utterance longer than `longest_s` is split at the next sentence end
  (a word ending in ".", "?" or "!"), so the decision model never waits for
  a monologue to end;
- overlapping speech gets no special handling.

A run can only be emitted once it is known not to be a false switch: when
the next speaker has said more than `false_switch_max_words` words, or the
segment ends.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from .stt import Word


@dataclass(frozen=True)
class Utterance:
    speaker: str
    words: tuple[Word, ...]

    @property
    def text(self) -> str:
        """The words joined as speech-to-text wrote them."""
        raise NotImplementedError

    @property
    def start_ms(self) -> int:
        return self.words[0].start_ms

    @property
    def end_ms(self) -> int:
        return self.words[-1].end_ms


class Splitter:
    def __init__(self, false_switch_max_words: int, longest_s: float) -> None:
        raise NotImplementedError

    def add(self, words: Iterable[Word]) -> list[Utterance]:
        """Take more final words; return the utterances now complete."""
        raise NotImplementedError

    def endpoint(self) -> list[Utterance]:
        """The segment ended (the provider's endpoint, Pause's finalise, or the
        stream's end): return every utterance still held."""
        raise NotImplementedError
