import hashlib

import pytest

from carl.prompts import FILLS, PromptError, load_prompts

from .conftest import ROOT

FINDING = """Search the web for {candidate}.
Write in {card_language}. Answer with JSON like {"outcome": "not found"}.
"""


@pytest.fixture
def folder(tmp_path):
    (tmp_path / "fact-finding.md").write_text(FINDING)
    (tmp_path / "decision.md").write_text("# Question\n\nIs `utterance` worth checking?\n")
    (tmp_path / "README.md").write_text("Not a prompt: {anything}\n")
    return tmp_path


FILLED = {"fact-finding": {"candidate", "card_language"}, "decision": set()}


def test_prompts_load_with_their_versions(folder):
    prompts = load_prompts(folder, FILLED)
    assert set(prompts) == {"fact-finding", "decision"}
    finding = prompts["fact-finding"]
    assert finding.placeholders == {"candidate", "card_language"}
    assert finding.version == hashlib.sha256(FINDING.encode()).hexdigest()[:8]
    assert len(finding.version) == 8


def test_a_prompt_is_filled_in(folder):
    finding = load_prompts(folder, FILLED)["fact-finding"]
    text = finding.render({"candidate": "Who played Rick?", "card_language": "Finnish"})
    assert text.startswith("Search the web for Who played Rick?.\nWrite in Finnish.")
    assert '{"outcome": "not found"}' in text  # JSON braces are not placeholders


def test_rendering_without_a_value_fails(folder):
    finding = load_prompts(folder, FILLED)["fact-finding"]
    with pytest.raises(PromptError, match="card_language"):
        finding.render({"candidate": "x"})


def test_a_placeholder_nothing_fills_stops_startup(folder):
    with pytest.raises(PromptError, match=r"fact-finding\.md: nothing fills \{card_language\}"):
        load_prompts(folder, {"fact-finding": {"candidate"}, "decision": set()})


def test_a_prompt_no_stage_fills_stops_startup_if_it_has_placeholders(folder):
    with pytest.raises(PromptError, match=r"fact-finding\.md: nothing fills \{candidate\}, \{card_language\}"):
        load_prompts(folder, {})
    (folder / "fact-finding.md").unlink()
    assert set(load_prompts(folder, {})) == {"decision"}


def test_a_missing_prompt_stops_startup(folder):
    with pytest.raises(PromptError, match=r"settle\.md: missing"):
        load_prompts(folder, FILLED | {"settle": set()})


def test_the_repos_prompts_load():
    prompts = load_prompts(ROOT / "prompts", FILLS)
    assert set(prompts) == set(FILLS)
