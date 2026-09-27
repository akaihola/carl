"""From final words to utterances (spec section 4, From final segments to utterances).

Pure logic, fed one stream's final words in order. An utterance is one
speaker's run of final words:

- a segment is split wherever the speaker label changes;
- a run of `false_switch_max_words` words or fewer between two runs by the
  same speaker is a false switch: the three runs become one utterance by that
  speaker. A short run at the start or end of a segment, or between two
  different speakers, is an utterance of its own;
- an utterance that has lasted `longest_s`, from its first word's start to
  the latest word's end, is split after its next sentence end (a word ending
  in ".", "?", "!" or "…"), so the decision model never waits for a monologue
  to end;
- overlapping speech gets no special handling.

Runs are decided left to right: a false switch is merged as soon as the
speaker before it speaks again. A run is held until it can no longer be part
of a merge: until the next speaker has said more than
`false_switch_max_words` words, a third speaker starts, or the segment ends.
An utterance split for length is emitted at once, with everything held
before it. The words after the split carry on as that speaker's next
utterance, so a false switch right after the split joins them.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from .stt import Word

SENTENCE_ENDS = (".", "?", "!", "…")


@dataclass(frozen=True)
class Utterance:
    """One speaker's words. Words merged in from a false switch keep their own speaker label."""

    speaker: str
    words: tuple[Word, ...]

    @property
    def text(self) -> str:
        """The words joined as speech-to-text wrote them."""
        return " ".join(w.text for w in self.words)

    @property
    def start_ms(self) -> int:
        return self.words[0].start_ms

    @property
    def end_ms(self) -> int:
        return self.words[-1].end_ms


@dataclass
class _Run:
    speaker: str
    words: list[Word] = field(default_factory=list)


class Splitter:
    def __init__(self, false_switch_max_words: int, longest_s: float) -> None:
        self._max_switch = false_switch_max_words
        self._longest_ms = longest_s * 1000
        # The held runs, at most two between words. Neighbours have different
        # speakers. The last may be empty: the speaker's words after a split
        # for length, still to come.
        self._runs: list[_Run] = []

    def add(self, words: Iterable[Word]) -> list[Utterance]:
        """Take more final words; return the utterances now complete."""
        done: list[Utterance] = []
        for word in words:
            done += self._add(word)
        return done

    def endpoint(self) -> list[Utterance]:
        """The segment ended (the provider's endpoint, Pause's finalise, or the
        stream's end): return every utterance still held."""
        return self._emit(len(self._runs))

    def _add(self, word: Word) -> list[Utterance]:
        runs, words = self._runs, [word]
        if not runs or runs[-1].speaker != word.speaker:
            if len(runs) > 1 and runs[-2].speaker == word.speaker and len(runs[-1].words) <= self._max_switch:
                words = runs.pop().words + words  # a false switch
            else:
                runs.append(_Run(word.speaker))
        done: list[Utterance] = []
        for w in words:
            run = runs[-1]
            run.words.append(w)
            if w.end_ms - run.words[0].start_ms >= self._longest_ms and w.text.endswith(SENTENCE_ENDS):
                done += self._emit(len(runs))
                runs.append(_Run(run.speaker))
        while len(runs) > 2 or (len(runs) == 2 and len(runs[1].words) > self._max_switch):
            done += self._emit(1)
        return done

    def _emit(self, n: int) -> list[Utterance]:
        """The first `n` held runs as utterances, no longer held."""
        done = [Utterance(r.speaker, tuple(r.words)) for r in self._runs[:n] if r.words]
        del self._runs[:n]
        return done
