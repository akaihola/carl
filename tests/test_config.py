import dataclasses
import datetime
import re

import pytest

from carl.config import ConfigError, parse_config

from .conftest import ROOT

TEXT = (ROOT / "config.toml").read_text()


def edited(old: str, new: str) -> str:
    assert TEXT.count(old) == 1, old
    return TEXT.replace(old, new)


def test_models_are_the_ones_step_0_confirmed(config):
    stages = {name: (s.provider, s.model) for name, s in vars(config.stages).items()}
    assert stages == {
        "speech_to_text": ("soniox", "stt-rt-v5"),
        "decision": ("openai", "gpt-6-luna"),
        "fact_finder_a": ("openai", "gpt-6-luna"),
        "fact_finder_b": ("perplexity", "google/gemini-3.8-flash"),
        "fact_checking": ("openrouter", "typesafe/jev-1.13"),
    }
    assert config.stages.speech_to_text.params["language_hints"] == ["fi", "en"]
    assert config.stages.speech_to_text.params["max_endpoint_delay_ms"] == 1500
    assert config.stages.decision.params["reasoning_effort"] == "none"
    assert config.stages.fact_finder_a.params == {"reasoning_effort": "none", "tool_choice": "required"}
    assert config.stages.fact_finder_b.params["search_type"] == "web"
    assert config.stages.fact_finder_b.params["max_steps"] == 2


def test_starting_values_are_the_specs(config):
    """Section 13's table, row by row."""
    c = config
    assert c.utterances.false_switch_max_words == 2
    assert c.utterances.longest_s == 30
    assert {"joo", "niin", "aha", "mm", "jaa", "okei", "yeah", "right", "uh-huh", "wow"} <= set(c.decision.backchannel)
    assert (c.decision.context_utterances, c.decision.context_window_s) == (10, 120)
    assert (c.decision.repeat_threshold, c.decision.candidate_threshold, c.decision.settle_threshold) == (0.5, 0.5, 0.5)
    assert (c.candidates.max_live, c.candidates.timeout_s) == (8, 60)
    assert (c.candidates.second_finder_wait_s, c.candidates.source_download_timeout_s) == (12, 3)
    assert dataclasses.astuple(c.bands) == (0.7, 0.85, 0.5, 0.6)
    assert "reddit.com" in c.sources.blocklist and "wikipedia.org" not in c.sources.blocklist
    assert (c.card_language.window_s, c.card_language.min_words) == (600, 50)
    assert (c.screen.min_on_screen_s, c.screen.late_card_s) == (8, 20)
    assert (c.connection.heartbeat_s, c.connection.silence_s) == (3, 10)
    assert (c.connection.reconnect_grace_s, c.connection.handover_s) == (120, 50 * 60)
    assert (c.outages.no_audio_s, c.outages.decision_failures, c.outages.check_failures) == (5, 3, 2)
    assert c.location.new_fix_distance_m == 500
    assert (c.location.town_only_accuracy_m, c.location.no_location_accuracy_m) == (1000, 20000)
    assert c.location.geocode_min_interval_s == 60
    assert c.currency.ecb_usd_per_eur == 1.1403
    assert c.currency.ecb_rate_date == datetime.date(2026, 9, 25)


def test_every_stage_has_a_price(config):
    for stage in vars(config.stages).values():
        assert config.price(stage)
    assert config.price(config.stages.speech_to_text).audio_hour == 0.12
    assert config.price(config.stages.fact_finder_a).search == 0.01
    assert config.price(config.stages.fact_finder_b).search == 0.0025


def test_the_page_gets_what_it_needs(config):
    assert config.page_values() == {
        "connection": {"heartbeat_s": 3, "silence_s": 10, "handover_s": 3000},
        "screen": {"min_on_screen_s": 8, "late_card_s": 20},
        "location": {"new_fix_distance_m": 500, "town_only_accuracy_m": 1000, "no_location_accuracy_m": 20000},
    }


def test_the_version_is_a_short_hash_of_the_file(config):
    assert re.fullmatch(r"[0-9a-f]{8}", config.version)
    assert parse_config(TEXT + "\n# a comment\n").version != config.version


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        ("max_live = 8\n", "", "missing setting max_live"),
        ("max_live = 8\n", "max_live = 8\nmax_lives = 8\n", "unknown setting max_lives"),
        ("[screen]\n", "[screens]\n", "unknown setting screens"),
        ("max_live = 8\n", 'max_live = "8"\n', "max_live: expected int"),
        ("max_live = 8\n", "max_live = 8.5\n", "max_live: expected int"),
        ("max_live = 8\n", "max_live = true\n", "max_live: expected int"),
        ("heartbeat_s = 3\n", "heartbeat_s = true\n", "heartbeat_s: expected float"),
        ("min_words = 50\n", "min_words = [50]\n", "min_words: expected int"),
        ('    "reddit.com",', "    1,", "blocklist: expected str"),
        ("hedged_supported = 0.6\n", "hedged_supported = 60\n", "hedged_supported must be between 0 and 1"),
        ("heartbeat_s = 3\n", "heartbeat_s = 10\n", "heartbeat_s must be shorter than silence_s"),
        ('model = "typesafe/jev-1.13"\n', 'model = "typesafe/jev-1.14"\n', "no price for stage fact_checking"),
        ("audio_hour = 0.12\n", "audio_hours = 0.12\n", "unknown setting audio_hours"),
        ("ecb_rate_date = 2026-09-25\n", 'ecb_rate_date = "2026-09-25"\n', "ecb_rate_date: expected date"),
        ("[currency]\n", "[currency\n", "config"),
    ],
)
def test_a_bad_config_stops_startup(old, new, message):
    with pytest.raises(ConfigError, match=re.escape(message)):
        parse_config(edited(old, new))


def test_ints_are_accepted_as_floats(config):
    assert parse_config(edited("longest_s = 30\n", "longest_s = 30.5\n")).utterances.longest_s == 30.5
    assert isinstance(config.utterances.longest_s, float)
