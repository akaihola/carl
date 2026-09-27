"""The typed-answer interface (spec section 3, Stage interfaces).

The decision and settle calls, the verdicts and the agreement call all ask a
`Question`: named text fields, one question and a choice of answers. They
get back a `TypedAnswer`: the chosen answer and a probability for each
choice, or no probabilities when the vendor gives none. Every call carries a
`CallRecord` for the recording and the cost; a failed call raises
`ModelError` with a typed kind and its record. Adapters never retry: the
pipeline decides what to do with each error.

An adapter per provider sits behind `make_typed_model`, selected by the
config file's stage. The typed prompt files are read by
`carl.models.questions.TypedPrompt`.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal, Protocol

import aiohttp

from ..config import Config, Stage

ErrorKind = Literal["timeout", "unavailable", "rate-limited", "bad output"]

# How long a typed call may take, end to end, before it is a `timeout`.
TYPED_TIMEOUT_S = 20.0


@dataclass(frozen=True)
class Question:
    """One typed call's input.

    `prompt` and `version` name the prompt file it came from. `choices` maps
    each answer the model may give to its description, with `same as Cn`
    already expanded to one choice per candidate id. `fields` are the named
    text fields the question is asked about.
    """

    prompt: str
    version: str
    text: str
    choices: Mapping[str, str]
    fields: Mapping[str, str]


@dataclass
class CallRecord:
    """Everything the recording, the cost and the failure log need from a call.

    - `model` is the id the provider reports it ran, or the configured one
      when no answer came back.
    - `params` are the stage's parameters from the config file; `request`
      is the exact body sent (never the headers, so never a key) and
      `response` the body that came back, `{"raw_text": …}` when it wasn't
      JSON, None when nothing came back.
    - `cost_usd` is Carl's figure from the price table, `provider_cost_usd`
      the provider's own when it reports one. When usage is unknown the
      token counts and the cost are an estimate and `estimated` is true.
    - On failure: `error` is the typed kind, `error_text` the provider's full
      error text (it may echo the prompt, so it belongs in a recording, never
      in the failure log), `status` the HTTP status and `error_code` the
      provider's error code, when there is one.
    """

    stage: str
    provider: str
    model: str
    prompt: str
    version: str
    fields: dict[str, str]
    params: dict[str, Any]
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    input_tokens: int | None = None
    cached_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: float = 0.0
    provider_cost_usd: float | None = None
    estimated: bool = False
    elapsed_s: float = 0.0
    request: dict[str, Any] | None = None
    response: Any = None
    status: int | None = None
    error: ErrorKind | None = None
    error_text: str = ""
    error_code: str | None = None

    @property
    def charged_usd(self) -> float:
        """What counts toward the totals: the provider's figure when it gives one."""
        return self.cost_usd if self.provider_cost_usd is None else self.provider_cost_usd

    def event(self) -> dict[str, Any]:
        """The record as a JSON-ready dict, for the recording's event log."""
        return asdict(self) | {"started_at": self.started_at.isoformat()}


@dataclass(frozen=True)
class TypedAnswer:
    """The chosen answer, one of the question's choices, and its call's record.

    `probs` maps each choice to its probability, or is None when the vendor
    gives none. Adapters that read probabilities from logprobs can't always
    tell every choice apart; their extra keys are:

    - `same as *`: choices that differ only in their candidate id (`same as
      C1`, `same as C2`…) pooled together. Only mass the model didn't take
      is pooled: when the chosen answer is itself a `same as Cn`, its
      probability and those of the ids it competed with are given one by
      one. So when the pooled `same as` total wins, the most likely single
      `same as Cn` is known unless the model chose a different kind of
      answer, in which case `same as *` holds all of it and no id can be
      named.
    - `ambiguous`: mass that could be several different choices.
    - `other`: mass on text that is none of the choices, or that the top
      logprobs didn't cover.

    The values add up to 1.
    """

    answer: str
    probs: dict[str, float] | None
    record: CallRecord


class ModelError(Exception):
    """A typed failure, with the call's record (cost included)."""

    def __init__(self, kind: ErrorKind, record: CallRecord):
        # The message holds no provider text: some providers' messages echo
        # the prompt. The full text is in `record.error_text`.
        status = f" (HTTP {record.status})" if record.status else ""
        super().__init__(f"{record.stage} via {record.provider}: {kind}{status}")
        self.kind = kind
        self.record = record


class TypedModel(Protocol):
    async def ask(self, question: Question, *, stage: str) -> TypedAnswer:
        """Ask one typed question. `stage` names the call in the record and
        the failure log: `decision`, `settle` or `fact-checking`.

        Raises ModelError on failure. Never retries.
        """


def http_session() -> aiohttp.ClientSession:
    """The one HTTP session the model adapters share.

    It honours the environment's proxy settings (HTTPS_PROXY).
    """
    return aiohttp.ClientSession(trust_env=True)


def make_typed_model(
    stage: Stage,
    config: Config,
    secrets: Mapping[str, str],
    session: aiohttp.ClientSession,
    *,
    timeout_s: float = TYPED_TIMEOUT_S,
    base_url: str | None = None,
) -> TypedModel:
    """The adapter the config file selects for `stage`, with its key from
    `secrets` and its prices from the config's price table.

    `base_url` points the adapter somewhere else, such as a test's fake
    server. Raises ValueError for an unknown provider, an unknown parameter,
    a missing price or a missing key.
    """
    if stage.provider == "openai":
        from .openai import OpenAITyped as adapter
    elif stage.provider == "openrouter":
        from .openrouter import JevTyped as adapter
    else:
        raise ValueError(f"no typed-answer adapter for provider {stage.provider!r}")
    key = secrets.get(adapter.key_name)
    if not key:
        raise ValueError(f"{adapter.key_name} is not set")
    return adapter(stage, config.price(stage), key, session, timeout_s=timeout_s, base_url=base_url)
