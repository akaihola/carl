import pytest

from carl.stt import Word
from carl.utterances import Splitter, Utterance

WORD_MS = 400


def talk(*turns: tuple[str, str], start_ms: int = 0, language: str = "fi") -> list[Word]:
    """Final words for each (speaker, text) turn, back to back, WORD_MS each."""
    words = []
    for speaker, text in turns:
        for part in text.split():
            words.append(Word(part, start_ms, start_ms + WORD_MS, speaker, language, True))
            start_ms += WORD_MS
    return words


def said(utterances: list[Utterance]) -> list[tuple[str, str]]:
    return [(u.speaker, u.text) for u in utterances]


def split(*turns: tuple[str, str], language: str = "fi", max_switch: int = 2) -> list[tuple[str, str]]:
    """The utterances of one segment."""
    splitter = Splitter(max_switch, 30)
    return said(splitter.add(talk(*turns, language=language)) + splitter.endpoint())


def feed(splitter: Splitter, words: list[Word]) -> list[tuple[int, str, str]]:
    """Each utterance with the index of the word that completed it, one word
    at a time, then the endpoint's with index -1."""
    out = [(i, u.speaker, u.text) for i, w in enumerate(words) for u in splitter.add([w])]
    return out + [(-1, u.speaker, u.text) for u in splitter.endpoint()]


def monologue(sentences: int, words_per_sentence: int = 10) -> str:
    """Sentences of `words_per_sentence` words, each ending in a full stop."""
    return " ".join(" ".join(["sana"] * (words_per_sentence - 1) + [f"loppu{n}."]) for n in range(sentences))


# --- Utterance ------------------------------------------------------------------


def test_text_joins_the_words_with_single_spaces_and_keeps_their_punctuation():
    utterance = Utterance("A", tuple(talk(("A", "Kuka se oli, se näyttelijä…"), start_ms=1_000)))
    assert utterance.text == "Kuka se oli, se näyttelijä…"
    assert (utterance.start_ms, utterance.end_ms) == (1_000, 1_000 + 5 * WORD_MS)


# --- Empty input and single words -------------------------------------------------


def test_no_words_give_no_utterances():
    splitter = Splitter(2, 30)
    assert splitter.add([]) == []
    assert splitter.endpoint() == []


def test_a_single_word_is_held_until_the_segment_ends():
    splitter = Splitter(2, 30)
    assert splitter.add(talk(("A", "Moi."))) == []
    assert said(splitter.endpoint()) == [("A", "Moi.")]
    assert splitter.endpoint() == []


def test_one_speaker_is_one_utterance_held_until_the_segment_ends():
    splitter = Splitter(2, 30)
    words = talk(("A", "The Great Wall is visible from space."), language="en")
    assert splitter.add(words) == []
    [utterance] = splitter.endpoint()
    assert utterance.words == tuple(words)
    assert (utterance.start_ms, utterance.end_ms) == (0, 7 * WORD_MS)


# --- Speaker changes ------------------------------------------------------------


def test_a_speaker_change_splits_the_segment():
    assert split(("A", "Suomi itsenäistyi vuonna 1918."), ("B", "Eikö se ollut 1917?")) == [
        ("A", "Suomi itsenäistyi vuonna 1918."),
        ("B", "Eikö se ollut 1917?"),
    ]
    assert split(("A", "Lightning never strikes twice."), ("B", "That's a myth, actually."), language="en") == [
        ("A", "Lightning never strikes twice."),
        ("B", "That's a myth, actually."),
    ]


def test_an_utterance_is_emitted_once_the_next_speaker_has_said_more_than_the_limit():
    words = talk(("A", "Suomi itsenäistyi vuonna 1918."), ("B", "Eikö se ollut 1917?"))
    assert feed(Splitter(2, 30), words) == [
        (6, "A", "Suomi itsenäistyi vuonna 1918."),
        (-1, "B", "Eikö se ollut 1917?"),
    ]


def test_several_speakers_take_turns():
    turns = (
        ("A", "Who played Rick in Casablanca?"),
        ("B", "Se oli Humphrey Bogart."),
        ("C", "No, it was Cary Grant."),
        ("A", "Oletko ihan varma siitä?"),
    )
    assert split(*turns) == list(turns)


# --- False switches -------------------------------------------------------------


@pytest.mark.parametrize(
    "language, before, switch, after",
    [
        ("fi", "Eiffel-torni valmistui vuonna", "tuota", "1889 Pariisin maailmannäyttelyyn."),
        ("fi", "Eiffel-torni valmistui vuonna", "no siis", "1889 Pariisin maailmannäyttelyyn."),
        ("en", "The Eiffel Tower was finished in", "uh", "1889 for the World's Fair."),
        ("en", "The Eiffel Tower was finished in", "I think", "1889 for the World's Fair."),
    ],
)
def test_one_or_two_words_between_the_same_speaker_are_a_false_switch(language, before, switch, after):
    splitter = Splitter(2, 30)
    words = talk(("A", before), ("B", switch), ("A", after), language=language)
    assert splitter.add(words) == []
    [utterance] = splitter.endpoint()
    assert (utterance.speaker, utterance.text) == ("A", f"{before} {switch} {after}")
    assert utterance.words == tuple(words)
    assert {w.speaker for w in utterance.words} == {"A", "B"}


@pytest.mark.parametrize(
    "language, switch",
    [("fi", "ei se ollut"), ("en", "no it wasn't")],
)
def test_three_words_between_the_same_speaker_are_an_utterance_of_their_own(language, switch):
    turns = (("A", "Napoleon oli tosi lyhyt."), ("B", switch), ("A", "Kaikki tietää sen."))
    words = talk(*turns, language=language)
    assert feed(Splitter(2, 30), words) == [
        (6, "A", "Napoleon oli tosi lyhyt."),
        (9, "B", switch),
        (-1, "A", "Kaikki tietää sen."),
    ]


def test_the_limit_comes_from_the_config():
    turns = (("A", "Napoleon oli tosi lyhyt."), ("B", "ei se ollut"), ("A", "Kaikki tietää sen."))
    assert split(*turns, max_switch=3) == [("A", "Napoleon oli tosi lyhyt. ei se ollut Kaikki tietää sen.")]
    assert split(("A", "Napoleon oli"), ("B", "joo"), ("A", "lyhyt."), max_switch=0) == [
        ("A", "Napoleon oli"),
        ("B", "joo"),
        ("A", "lyhyt."),
    ]


def test_a_short_run_at_the_start_of_a_segment_is_an_utterance():
    assert split(("B", "Joo."), ("A", "Suomi itsenäistyi vuonna 1917.")) == [
        ("B", "Joo."),
        ("A", "Suomi itsenäistyi vuonna 1917."),
    ]


def test_a_short_run_at_the_end_of_a_segment_is_an_utterance():
    words = talk(("A", "Goldfish have a three-second memory."), ("B", "Not true."), language="en")
    assert feed(Splitter(2, 30), words) == [
        (-1, "A", "Goldfish have a three-second memory."),
        (-1, "B", "Not true."),
    ]


def test_a_short_run_between_two_different_speakers_is_an_utterance():
    turns = (("A", "Mount Everest is the tallest mountain."), ("B", "Hmm."), ("C", "Mauna Kea is taller."))
    words = talk(*turns, language="en")
    assert feed(Splitter(2, 30), words) == [
        (7, "A", "Mount Everest is the tallest mountain."),
        (9, "B", "Hmm."),
        (-1, "C", "Mauna Kea is taller."),
    ]


def test_a_short_run_between_two_short_runs_by_the_same_speaker_is_merged():
    assert split(("B", "Ai"), ("A", "no"), ("B", "niin tietysti.")) == [("B", "Ai no niin tietysti.")]


def test_merges_are_decided_left_to_right():
    # "juu" is a false switch inside A's turn, so "ja" rejoins A and B's run
    # afterwards is B's own.
    turns = (("A", "Kuu on juustoa"), ("B", "juu"), ("A", "ja"), ("B", "Ei todellakaan ole."))
    assert split(*turns) == [("A", "Kuu on juustoa juu ja"), ("B", "Ei todellakaan ole.")]


def test_a_new_segment_starts_afresh():
    splitter = Splitter(2, 30)
    assert splitter.add(talk(("A", "Kuka ohjasi Tuntemattoman sotilaan?"))) == []
    assert said(splitter.endpoint()) == [("A", "Kuka ohjasi Tuntemattoman sotilaan?")]
    words = talk(("B", "Edvin Laine."), ("A", "Aivan, niin ohjasi."), start_ms=10_000)
    assert said(splitter.add(words) + splitter.endpoint()) == [("B", "Edvin Laine."), ("A", "Aivan, niin ohjasi.")]


def test_how_words_arrive_does_not_change_the_utterances():
    words = talk(
        ("A", "The Great Wall is"), ("B", "uh"), ("A", "visible from space."),
        ("B", "Ei näy, se on myytti."), ("C", "Oikeesti?"), ("B", "Joo, astronautit ovat sanoneet niin."),
        ("A", "Oh."), ("C", "Hyvä tietää."),
    )  # fmt: skip
    splitter = Splitter(2, 30)
    whole = said(splitter.add(words) + splitter.endpoint())
    assert whole == [
        ("A", "The Great Wall is uh visible from space."),
        ("B", "Ei näy, se on myytti. Oikeesti? Joo, astronautit ovat sanoneet niin."),
        ("A", "Oh."),
        ("C", "Hyvä tietää."),
    ]
    for size in (1, 2, 3, 5, 7):
        chunks = [words[i : i + size] for i in range(0, len(words), size)]
        assert said([u for chunk in chunks for u in splitter.add(chunk)] + splitter.endpoint()) == whole


# --- Long utterances ------------------------------------------------------------


def test_a_long_monologue_is_split_at_the_first_sentence_end_after_the_limit():
    # Ten 400 ms words a sentence: 30 s is reached at the 75th word, and the
    # next sentence ends at the 80th, at 32 s.
    words = talk(("A", monologue(12)))
    out = feed(Splitter(2, 30), words)
    assert [(i, speaker) for i, speaker, _ in out] == [(79, "A"), (-1, "A")]
    assert out[0][2] == monologue(8)
    assert out[1][2] == monologue(12)[len(monologue(8)) + 1 :]


def test_every_part_of_a_long_monologue_is_measured_from_its_own_start():
    words = talk(("A", monologue(20)), start_ms=600_000)
    utterances = Splitter(2, 30).add(words)
    assert [len(u.words) for u in utterances] == [80, 80]
    assert all(u.end_ms - u.start_ms == 32_000 for u in utterances)


@pytest.mark.parametrize("language, text", [("fi", "ja sitten " * 50), ("en", "and then " * 50)])
def test_a_long_monologue_without_a_sentence_end_waits_for_the_segment_end(language, text):
    splitter = Splitter(2, 30)
    assert splitter.add(talk(("A", text), language=language)) == []
    [utterance] = splitter.endpoint()
    assert utterance.end_ms - utterance.start_ms == 40_000


@pytest.mark.parametrize("mark", [".", "?", "!", "…"])
def test_a_split_falls_exactly_at_the_limit(mark):
    words = [
        Word("Tämä", 5_000, 20_000, "A", "fi", True),
        Word(f"loppui{mark}", 20_000, 35_000, "A", "fi", True),
        Word("Uusi", 35_000, 35_400, "A", "fi", True),
    ]
    out = feed(Splitter(2, 30), words)
    assert out == [(1, "A", f"Tämä loppui{mark}"), (-1, "A", "Uusi")]


def test_a_sentence_end_just_before_the_limit_does_not_split():
    words = [
        Word("Tämä", 5_000, 20_000, "A", "fi", True),
        Word("loppui.", 20_000, 34_999, "A", "fi", True),
        Word("Tämä", 35_000, 35_400, "A", "fi", True),
        Word("toinen", 35_400, 35_800, "A", "fi", True),
        Word("myös.", 35_800, 36_200, "A", "fi", True),
        Word("Uusi", 36_200, 36_600, "A", "fi", True),
    ]
    assert feed(Splitter(2, 30), words) == [(4, "A", "Tämä loppui. Tämä toinen myös."), (-1, "A", "Uusi")]


def test_a_comma_is_not_a_sentence_end():
    words = [Word("No,", 0, 31_000, "A", "fi", True), Word("niin.", 31_000, 31_400, "A", "fi", True)]
    assert feed(Splitter(2, 30), words) == [(1, "A", "No, niin.")]


def test_a_speaker_change_ends_a_long_utterance_without_waiting_for_a_sentence_end():
    words = talk(("A", "ja sitten " * 50), ("B", "Anteeksi mutta nyt"))
    out = feed(Splitter(2, 30), words)
    assert [(i, speaker) for i, speaker, _ in out] == [(102, "A"), (-1, "B")]


def test_a_false_switch_after_a_split_joins_the_words_that_follow():
    turns = (("A", monologue(8)), ("B", "mm"), ("A", "ja sitten vielä."))
    out = feed(Splitter(2, 30), talk(*turns))
    assert out == [(79, "A", monologue(8)), (-1, "A", "mm ja sitten vielä.")]


def test_a_short_run_after_a_split_is_an_utterance_when_the_speaker_does_not_return():
    turns = (("A", monologue(8)), ("B", "Ai jaa."), ("C", "Mielenkiintoista, kerro lisää."))
    out = feed(Splitter(2, 30), talk(*turns))
    assert out == [(79, "A", monologue(8)), (84, "B", "Ai jaa."), (-1, "C", "Mielenkiintoista, kerro lisää.")]


def test_a_long_utterance_is_held_while_a_short_run_might_be_a_false_switch():
    # A's 75 words pass the limit with no sentence end; B's "Joo." isn't
    # A's until A speaks again, and then it is the sentence end A splits at.
    turns = (("A", "sana " * 75), ("B", "Joo."), ("A", "No niin."))
    out = feed(Splitter(2, 30), talk(*turns))
    assert out == [(76, "A", "sana " * 75 + "Joo."), (-1, "A", "No niin.")]


def test_a_split_emits_what_is_held_before_it():
    # B's 2 words wait to see whether A returns; B's third word both makes
    # the run B's own and ends B's 30 s utterance.
    words = [
        *talk(("A", "Se oli Bogart.")),
        Word("Ei", 1_200, 1_600, "B", "fi", True),
        Word("vaan", 1_600, 2_000, "B", "fi", True),
        Word("Grant.", 2_000, 31_200, "B", "fi", True),
        Word("Kyllä", 31_200, 31_600, "B", "fi", True),
    ]
    out = feed(Splitter(2, 30), words)
    assert out == [(5, "A", "Se oli Bogart."), (5, "B", "Ei vaan Grant."), (-1, "B", "Kyllä")]
