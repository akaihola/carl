"""The config file (First working Carl spec, section 13).

The loader is strict: a missing setting, an unknown one or a wrong type stops
the server at startup, so a typo can't fall back to a default unnoticed.
"""

from __future__ import annotations

import dataclasses
import datetime
import hashlib
import tomllib
import types
import typing
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class Stage:
    provider: str
    model: str
    params: dict[str, Any]


@dataclass(frozen=True)
class Stages:
    speech_to_text: Stage
    decision: Stage
    fact_finder_a: Stage
    fact_finder_b: Stage
    fact_checking: Stage


@dataclass(frozen=True)
class Utterances:
    false_switch_max_words: int
    longest_s: float


@dataclass(frozen=True)
class Decision:
    backchannel: tuple[str, ...]
    context_utterances: int
    context_window_s: float
    repeat_threshold: float
    candidate_threshold: float
    settle_threshold: float

    def __post_init__(self) -> None:
        _probabilities(self, "repeat_threshold", "candidate_threshold", "settle_threshold")


@dataclass(frozen=True)
class Candidates:
    max_live: int
    timeout_s: float
    second_finder_wait_s: float
    source_download_timeout_s: float


@dataclass(frozen=True)
class Bands:
    plain_same_fact: float
    plain_supported_shown: float
    plain_supported_other: float
    hedged_supported: float

    def __post_init__(self) -> None:
        _probabilities(self, *(f.name for f in dataclasses.fields(self)))


@dataclass(frozen=True)
class Sources:
    blocklist: tuple[str, ...]


@dataclass(frozen=True)
class CardLanguage:
    window_s: float
    min_words: int


@dataclass(frozen=True)
class Screen:
    min_on_screen_s: float
    late_card_s: float


@dataclass(frozen=True)
class Connection:
    heartbeat_s: float
    silence_s: float
    reconnect_grace_s: float
    handover_s: float

    def __post_init__(self) -> None:
        if self.heartbeat_s >= self.silence_s:
            raise ConfigError("heartbeat_s must be shorter than silence_s")


@dataclass(frozen=True)
class Outages:
    no_audio_s: float
    decision_failures: int
    check_failures: int


@dataclass(frozen=True)
class Location:
    new_fix_distance_m: float
    town_only_accuracy_m: float
    no_location_accuracy_m: float
    geocode_min_interval_s: float


@dataclass(frozen=True)
class Price:
    """USD: per million tokens, per search call and per hour of audio."""

    input: float | None = None
    cached: float | None = None
    output: float | None = None
    search: float | None = None
    audio_hour: float | None = None


@dataclass(frozen=True)
class Currency:
    ecb_usd_per_eur: float
    ecb_rate_date: datetime.date


@dataclass(frozen=True)
class Config:
    stages: Stages
    utterances: Utterances
    decision: Decision
    candidates: Candidates
    bands: Bands
    sources: Sources
    card_language: CardLanguage
    screen: Screen
    connection: Connection
    outages: Outages
    location: Location
    prices: dict[str, dict[str, Price]]
    currency: Currency
    # The file as it was read, for the copy each recording stores.
    text: str = dataclasses.field(default="", compare=False, repr=False, metadata={"in_file": False})

    @property
    def version(self) -> str:
        """A short content hash of the file, like a prompt's version."""
        return hashlib.sha256(self.text.encode()).hexdigest()[:8]

    def price(self, stage: Stage) -> Price:
        return self.prices[stage.provider][stage.model]

    def page_values(self) -> dict[str, dict[str, float]]:
        """The settings the page needs itself, sent to it at session start."""
        c, s, loc = self.connection, self.screen, self.location
        return {
            "connection": {"heartbeat_s": c.heartbeat_s, "silence_s": c.silence_s, "handover_s": c.handover_s},
            "screen": {"min_on_screen_s": s.min_on_screen_s, "late_card_s": s.late_card_s},
            "location": {
                "new_fix_distance_m": loc.new_fix_distance_m,
                "town_only_accuracy_m": loc.town_only_accuracy_m,
                "no_location_accuracy_m": loc.no_location_accuracy_m,
            },
        }


def load_config(path: Path) -> Config:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        raise ConfigError(f"{path}: {e.strerror}") from e
    return parse_config(text, str(path))


def parse_config(text: str, where: str = "config") -> Config:
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"{where}: {e}") from e
    config = dataclasses.replace(_build(Config, data, where), text=text)
    for name, stage in vars(config.stages).items():
        if stage.model not in config.prices.get(stage.provider, {}):
            raise ConfigError(f"{where}: no price for stage {name}'s model {stage.provider} {stage.model}")
    return config


def _build(cls: type, data: Any, where: str) -> Any:
    """Build dataclass `cls` from a TOML table, checking every key and type."""
    if not isinstance(data, dict):
        raise ConfigError(f"{where}: expected a table")
    hints = typing.get_type_hints(cls)
    fields = {f.name: f for f in dataclasses.fields(cls) if f.metadata.get("in_file", True)}
    unknown = sorted(data.keys() - fields.keys())
    if unknown:
        raise ConfigError(f"{where}: unknown setting {', '.join(unknown)}")
    required = [
        n for n, f in fields.items() if f.default is dataclasses.MISSING and f.default_factory is dataclasses.MISSING
    ]
    missing = [n for n in required if n not in data]
    if missing:
        raise ConfigError(f"{where}: missing setting {', '.join(missing)}")
    values = {name: _value(hints[name], value, f"{where}: {name}") for name, value in data.items()}
    try:
        return cls(**values)
    except ConfigError as e:
        raise ConfigError(f"{where}: {e}") from None


def _value(hint: Any, value: Any, where: str) -> Any:
    if dataclasses.is_dataclass(hint):
        return _build(hint, value, where)
    origin, args = typing.get_origin(hint), typing.get_args(hint)
    if origin is types.UnionType:  # `float | None`: TOML has no null, so the value is a float
        return _value(args[0], value, where)
    if origin is tuple:
        if not isinstance(value, list):
            raise ConfigError(f"{where}: expected a list")
        return tuple(_value(args[0], item, where) for item in value)
    if origin is dict:
        if not isinstance(value, dict):
            raise ConfigError(f"{where}: expected a table")
        return {key: _value(args[1], item, f"{where}.{key}") for key, item in value.items()}
    if hint is Any:
        return value
    if hint is float and isinstance(value, int) and not isinstance(value, bool):
        return float(value)
    # bool is an int in Python, but `true` is never a valid number here.
    if not isinstance(value, hint) or (hint is int and isinstance(value, bool)):
        raise ConfigError(f"{where}: expected {hint.__name__}, got {type(value).__name__} {value!r}")
    return value


def _probabilities(section: Any, *names: str) -> None:
    for name in names:
        if not 0 <= getattr(section, name) <= 1:
            raise ConfigError(f"{name} must be between 0 and 1")
