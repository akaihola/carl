"""What the HTTP model adapters share: the POST with its typed errors, and
the cost from the price table or an estimate (spec sections 3 and 11).

Typed errors:

- `timeout`: no full answer within the call's timeout.
- `unavailable`: the provider couldn't be reached or refused to run the
  call: a transport error, a 5xx, or a 4xx other than 429 (a bad key, no
  credits left, a request it won't take). No output came back, so none of
  it can be bad; the HTTP status and the provider's error code tell these
  apart in the failure log.
- `rate-limited`: HTTP 429.
- `bad output`: the provider answered, but the answer can't be used: not
  JSON, not one of the choices, a refusal, an incomplete run.

A call whose usage is unknown (no usage in the response, which covers every
timeout and transport error) is charged an estimate, marked as such: the
JSON request body's characters over CHARS_PER_TOKEN as input tokens, plus
the adapter's typical output size. A rejected request is probably not
billed, but Carl can't know, so it is estimated like the rest; estimates are
kept apart in the totals.
"""

from __future__ import annotations

import json
import math
import time
from typing import Any, ClassVar

import aiohttp

from ..config import Price, Stage
from . import TYPED_TIMEOUT_S, CallRecord, ErrorKind, ModelError, Question

# About 4 characters a token, the usual rule of thumb for English. Finnish
# takes more tokens a character, the JSON around the text fewer.
CHARS_PER_TOKEN = 4


def token_cost(price: Price, input_tokens: int, cached_tokens: int, output_tokens: int) -> float:
    """USD at the price table's rates per million tokens.

    Cached tokens are part of the input tokens. With no cached price they
    cost as much as the rest of the input.
    """
    input_price, output_price = price.input or 0.0, price.output or 0.0
    cached_price = input_price if price.cached is None else price.cached
    uncached = max(0, input_tokens - cached_tokens)
    return (uncached * input_price + cached_tokens * cached_price + output_tokens * output_price) / 1_000_000


def error_code(body: Any) -> str | None:
    """The provider's error code from an error body, such as OpenAI's `rate_limit_exceeded`."""
    error = body.get("error") if isinstance(body, dict) else None
    if not isinstance(error, dict):
        return None
    code = error.get("code") or error.get("type")
    return None if code is None else str(code)


class HttpAdapter:
    """A typed-answer adapter that POSTs one JSON request per call.

    A subclass names its provider, key, URL, the stage parameters it knows
    and its typical output size, and implements `ask`.
    """

    provider: ClassVar[str]
    key_name: ClassVar[str]
    default_base_url: ClassVar[str]
    path: ClassVar[str]
    known_params: ClassVar[frozenset[str]]
    typical_output_tokens: ClassVar[int]

    def __init__(
        self,
        stage: Stage,
        price: Price,
        key: str,
        session: aiohttp.ClientSession,
        *,
        timeout_s: float = TYPED_TIMEOUT_S,
        base_url: str | None = None,
    ) -> None:
        unknown = stage.params.keys() - self.known_params
        if unknown:
            raise ValueError(f"{self.provider} {stage.model}: unknown parameter {', '.join(sorted(unknown))}")
        if price.input is None or price.output is None:
            raise ValueError(f"{self.provider} {stage.model}: the price table needs input and output prices")
        self.stage, self.price, self.session, self.timeout_s = stage, price, session, timeout_s
        self.url = (base_url or self.default_base_url).rstrip("/") + self.path
        self._headers = {"Authorization": f"Bearer {key}"}

    def start(self, question: Question, stage: str, request: dict[str, Any]) -> CallRecord:
        return CallRecord(
            stage, self.provider, self.stage.model, question.prompt, question.version,
            dict(question.fields), dict(self.stage.params), request=request,
        )

    async def post(self, record: CallRecord) -> dict[str, Any]:
        """Send the record's request and return the JSON object that came back.

        Raises ModelError for a timeout, a transport error, an HTTP error or
        a body that isn't a JSON object.
        """
        start = time.perf_counter()
        try:
            async with self.session.post(
                self.url, json=record.request, headers=self._headers,
                timeout=aiohttp.ClientTimeout(total=self.timeout_s),
            ) as response:
                record.status = response.status
                raw = (await response.read()).decode("utf-8", errors="replace")
        except TimeoutError as e:
            raise self.fail(record, "timeout", f"no answer within {self.timeout_s:g} s ({type(e).__name__})") from None
        except aiohttp.ClientError as e:
            raise self.fail(record, "unavailable", f"{type(e).__name__}: {e}") from None
        finally:
            record.elapsed_s = time.perf_counter() - start
        try:
            body = json.loads(raw)
        except ValueError:
            body = None
        record.response = {"raw_text": raw} if body is None else body
        if not 200 <= response.status < 300:
            record.error_code = error_code(body)
            raise self.fail(record, "rate-limited" if response.status == 429 else "unavailable",
                            f"HTTP {response.status}: {raw}")
        if not isinstance(body, dict):
            raise self.fail(record, "bad output", f"not a JSON object: {raw}")
        return body

    def charge(
        self, record: CallRecord, input_tokens: int, cached_tokens: int, output_tokens: int,
        provider_cost: float | None = None,
    ) -> None:
        record.input_tokens, record.cached_tokens, record.output_tokens = input_tokens, cached_tokens, output_tokens
        record.cost_usd = token_cost(self.price, input_tokens, cached_tokens, output_tokens)
        record.provider_cost_usd = provider_cost

    def estimate(self, record: CallRecord) -> None:
        """Charge a call whose usage is unknown an estimate, marked as such."""
        sent = json.dumps(record.request, ensure_ascii=False)
        self.charge(record, math.ceil(len(sent) / CHARS_PER_TOKEN), 0, self.typical_output_tokens)
        record.estimated = True

    def fail(self, record: CallRecord, kind: ErrorKind, text: str) -> ModelError:
        """The typed error for a failed call, charged an estimate if it has no usage."""
        record.error, record.error_text = kind, text
        if record.input_tokens is None:
            self.estimate(record)
        return ModelError(kind, record)
