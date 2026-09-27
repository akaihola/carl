from collections import Counter

from carl.config import CardLanguage as Settings
from carl.language import CardLanguage, card_language, choose, count
from carl.session import Heard, Marker
from carl.stt.fake import words
from carl.utterances import Utterance

SETTINGS = Settings(window_s=600, min_words=50)
T0 = 1_790_000_000.0


def heard(n: int, text: str, at: float, language: str = "fi", speaker: str = "1") -> Heard:
    return Heard(f"U{n}", 1, Utterance(speaker, words(speaker, text, language=language)), T0 + at)


def fill(n: int) -> str:
    """`n` words, tagged with `heard`'s language."""
    return " ".join(["sana"] * n)


def test_the_language_with_the_most_words_wins():
    chosen = choose(Counter(fi=60, en=20), Counter(en=5), 50)
    assert chosen == CardLanguage("fi", "most words", {"fi": 60, "en": 20}, {"en": 5})


def test_below_the_word_minimum_the_candidates_own_language_is_used():
    chosen = choose(Counter(fi=30, en=19), Counter(en=6, fi=1), 50)
    assert chosen.language == "en" and chosen.rule == "too few words"
    assert chosen.window == {"fi": 30, "en": 19} and chosen.own == {"en": 6, "fi": 1}
    assert choose(Counter(fi=30, en=20), Counter(en=6), 50).rule == "most words"  # exactly the minimum


def test_on_a_tie_the_candidates_own_language_is_used():
    chosen = choose(Counter(fi=40, en=40), Counter(en=7), 50)
    assert chosen.language == "en" and chosen.rule == "tie"


def test_the_candidates_own_language_is_its_most_words_then_the_first_to_appear():
    assert choose(Counter(), Counter(en=2, fi=5), 50).language == "fi"
    assert choose(Counter(), Counter(en=3, fi=3), 50).language == "en"
    assert choose(Counter(), Counter(), 50).language == ""


def test_words_without_a_language_code_are_not_counted():
    tagged = words("1", "yksi kaksi", language="fi") + words("1", "three", language="")
    assert count(tagged) == {"fi": 2}


def test_the_window_is_the_last_ten_minutes_up_to_the_candidate():
    old = heard(1, fill(80), at=0, language="en")  # 601 s before the candidate: outside
    finnish = heard(2, fill(45), at=300)
    english = heard(3, fill(20), at=580, language="en")
    candidate = heard(4, "Einstein failed maths at school, you know.", at=601, language="en")
    chosen = card_language([old, finnish, Marker("paused", T0 + 590), english, candidate], candidate, SETTINGS)
    assert chosen == CardLanguage("fi", "most words", {"fi": 45, "en": 27}, {"en": 7})


def test_a_finnish_dinner_quoting_an_english_song_gets_a_finnish_card():
    dinner = [heard(i, fill(12), at=i * 30) for i in range(1, 6)]
    quote = heard(6, "Imagine all the people living for today, sanoi Lennon.", at=200, language="en")
    chosen = card_language([*dinner, quote], quote, SETTINGS)
    assert chosen.language == "fi" and chosen.window == {"fi": 60, "en": 9}


def test_early_in_a_session_the_candidate_speaks_for_itself():
    first = heard(1, "Helsingin olympialaiset oli vuonna 1956.", at=0)
    assert card_language([first], first, SETTINGS) == CardLanguage("fi", "too few words", {"fi": 5}, {"fi": 5})


def test_the_event_keeps_the_counts_behind_the_choice():
    chosen = CardLanguage("fi", "most words", {"fi": 60, "en": 20}, {"en": 5})
    assert chosen.event() == {"language": "fi", "rule": "most words",
                              "window_words": {"fi": 60, "en": 20}, "own_words": {"en": 5}}
