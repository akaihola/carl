"""Card language (spec section 7): the language a candidate's fact card is
written in, worked out by Carl from the language code on each word, never by
a model.

It is the language with the most words over the last `window_s` of final
utterances, up to and including the candidate. With fewer than `min_words`
words in that window, or a tie for the most, it is the candidate's own
language: the one most of its words are in, the first to appear on a tie.
Words with no language code aren't counted.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from .config import CardLanguage as Settings
from .session import Heard, Marker
from .stt import Word


@dataclass(frozen=True)
class CardLanguage:
    """The chosen language code (`fi`, `en`) and the word counts behind it.

    `rule` says why: `most words` in the window, or the candidate's own
    language because the window had `too few words` or a `tie`.
    """

    language: str
    rule: Literal["most words", "too few words", "tie"]
    window: dict[str, int]
    own: dict[str, int]

    def event(self) -> dict[str, Any]:
        return {"language": self.language, "rule": self.rule, "window_words": self.window, "own_words": self.own}


def count(words: Iterable[Word]) -> Counter[str]:
    """Words per language code, in the order the languages first appear."""
    return Counter(w.language for w in words if w.language)


def choose(window: Counter[str], own: Counter[str], min_words: int) -> CardLanguage:
    ranked = window.most_common(2)
    own_language = max(own, key=own.__getitem__, default="")
    if window.total() < min_words:
        return CardLanguage(own_language, "too few words", dict(window), dict(own))
    if len(ranked) == 2 and ranked[0][1] == ranked[1][1]:
        return CardLanguage(own_language, "tie", dict(window), dict(own))
    return CardLanguage(ranked[0][0], "most words", dict(window), dict(own))


def card_language(heard: Sequence[Heard | Marker], candidate: Heard, settings: Settings) -> CardLanguage:
    """The card language for `candidate`, from `heard`: the session's
    utterances and markers up to and including it."""
    window: list[Word] = []
    for item in heard:
        if isinstance(item, Heard) and candidate.time - item.time <= settings.window_s:
            window += item.utterance.words
    return choose(count(window), count(candidate.utterance.words), settings.min_words)
