"""The fact-finding models (spec sections 3 and 6): each candidate goes to
fact-finder A and fact-finder B, which search the web and write a draft card
themselves.

A `FindingRequest` holds the prompt (`prompts/fact-finding.md`, the same for
both) and the values the pipeline fills into it: the candidate's kind and
line, the decision call's context window, the place name with the local date,
time and timezone, and the card language by name. It also holds what each
search tool is told of where the table is: place names, never coordinates.

`FactFinder.find(request, stage=…)` returns a `Finding`: the outcome, the
candidate restated as one standalone sentence, and for `claim is wrong` and
`question answered` a complete `DraftCard`, with the search results the card
is matched against and the call's `CallRecord`. A failure raises
`ModelError`, typed as in `carl.models.calls`: `timeout`, `unavailable` (a
transport error, a 5xx, a 4xx other than 429, a run with status `failed`),
`rate-limited` (429) or `bad output` (not the JSON asked for, an unknown
outcome, no restatement, an incomplete card, a refusal, an unfinished run).
Adapters never retry.

- **Fact-finder A**: an OpenAI model such as GPT-6 Luna on the Responses API,
  with OpenAI's `web_search`, forced by `tool_choice`. Its results are the
  search calls' own sources: URLs, with titles when OpenAI gives them, and no
  text. With JSON output OpenAI gives no `url_citation`, so the card's source
  can only be looked for among these (step 0).
- **Fact-finder B**: a model pinned on Perplexity's Agent API, with
  Perplexity's `web_search`. Its results are the `search_results` items: URL,
  title and the snippet that B's excerpt must be a substring of.

**Cost:** tokens at the price table's rates, plus each search call at the
stage's `search` price. Perplexity's searches charged are its `search_web`
invocations, and one invocation can run several queries. Perplexity's own
figure is kept beside Carl's and counts toward the totals
(`CallRecord.charged_usd`); a difference is logged. A call whose usage is
unknown is charged an estimate, marked as such: the tokens Carl sent, the
typical output and the typical number of searches, or none for a request
refused with a 4xx (a 429 included), which ran no search.

Perplexity's rate limit can refuse requests sent at once: in the first run
of the example cases, on 2026-09-27, it answered 2 of 3 with a 429.

`store: false` is always sent to both, in code: it is a privacy choice, not a
setting.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from typing import Any, ClassVar, Literal, Protocol, get_args
from urllib.parse import unquote, urlsplit

import aiohttp

from .config import Config, Price, Stage
from .models import CallRecord
from .models.calls import HttpAdapter
from .prompts import Prompt

log = logging.getLogger(__name__)

# The failure log's names for the two fact-finders (spec section 10), for `stage`.
STAGE_A = "fact-finding A"
STAGE_B = "fact-finding B"

# Carl waits about 12 s for the second fact-finder after the first arrives,
# and a candidate fails 60 s after its utterance. Step 0 took 9 s at most.
FINDING_TIMEOUT_S = 30.0

Kind = Literal["claim", "open question"]
Outcome = Literal["claim is wrong", "claim is right", "question answered", "not found"]
KINDS: tuple[str, ...] = get_args(Kind)
OUTCOMES: tuple[str, ...] = get_args(Outcome)
# The outcomes that come with a draft card. The others end the candidate silently.
CARD_OUTCOMES = ("claim is wrong", "question answered")
CARD_FIELDS = ("title", "fact", "source_url", "source_title", "excerpt")

# The conversation field when the candidate was the first thing said.
NOTHING_BEFORE = "(nothing said before)"

# The prompt names the card language in English; Carl knows it by its code.
LANGUAGE_NAMES = {
    "fi": "Finnish", "en": "English", "sv": "Swedish", "et": "Estonian", "de": "German", "fr": "French",
    "es": "Spanish", "it": "Italian", "ru": "Russian",
}

# What each search tool may be told of where the table is: place names and
# the timezone, never coordinates (spec section 12). Anything else in a
# request's location is dropped.
OPENAI_LOCATION = ("city", "region", "country", "timezone")
PERPLEXITY_LOCATION = ("country", "region", "city")

# The draft card's JSON schema. Strict schemas need every property required,
# so the card's fields are empty strings for the outcomes without a card.
SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "restatement": {"type": "string"},
        "outcome": {"type": "string", "enum": list(OUTCOMES)},
        **{name: {"type": "string"} for name in CARD_FIELDS},
    },
    "required": ["restatement", "outcome", *CARD_FIELDS],
    "additionalProperties": False,
}
SCHEMA_NAME = "draft_card"

# Some models wrap their JSON in a code fence despite the schema.
FENCE = re.compile(r"^```(?:json)?\s*|\s*```$")
# A dated snapshot of a model: gpt-6-luna-2026-09-01 is gpt-6-luna.
DATED = re.compile(r"-(?:\d{4}-\d{2}-\d{2}|\d{8})$")


def language_name(code: str) -> str:
    """The card language's name for the prompt: `fi` is Finnish. An unknown
    code is given as it is."""
    return LANGUAGE_NAMES.get(code.lower(), code)


def kept(where: Mapping[str, Any] | None, keys: Sequence[str]) -> dict[str, str]:
    return {k: str(where[k]) for k in keys if where and where.get(k)}


def openai_location(where: Mapping[str, Any] | None) -> dict[str, str] | None:
    """OpenAI `web_search`'s `user_location`: `approximate`, with the city,
    region, country code and timezone it is given, and nothing else."""
    place = kept(where, OPENAI_LOCATION)
    return {"type": "approximate"} | place if place else None


def perplexity_location(where: Mapping[str, Any] | None) -> dict[str, str] | None:
    """Perplexity `web_search`'s `user_location`: the country code, region and
    city it is given, and nothing else."""
    return kept(where, PERPLEXITY_LOCATION) or None


@dataclass(frozen=True)
class FindingRequest:
    """One candidate, as both fact-finders are given it (spec section 6).

    - `prompt`: `prompts/fact-finding.md`, filled in with the values below.
    - `candidate_kind`: `claim` or `open question`, as the decision call found.
    - `candidate`: the candidate's line, `A2: text`. `conversation`: the
      lines of the decision call's context window before it, oldest first,
      with its `(paused)` and `(gap)` markers.
    - `place_and_time`: the place name with the local date, time and
      timezone (`Locator.place_and_time(session, with_place=True)`).
    - `card_language`: the card language by name, `Finnish` (`language_name`).
    - `openai_location`, `perplexity_location`: each search tool's
      `user_location` (`Locator.openai_user_location(session)`,
      `Locator.perplexity_user_location(session)`), or None to send none.
      Only place names and the timezone are ever sent from them.
    """

    prompt: Prompt
    candidate_kind: str
    candidate: str
    conversation: Sequence[str]
    place_and_time: str
    card_language: str
    openai_location: Mapping[str, str] | None = None
    perplexity_location: Mapping[str, str] | None = None

    def __post_init__(self) -> None:
        if self.candidate_kind not in KINDS:
            raise ValueError(f"a candidate is a claim or an open question, not {self.candidate_kind!r}")
        object.__setattr__(self, "conversation", tuple(self.conversation))

    def values(self) -> dict[str, str]:
        """The values filled into the prompt: a replay rebuilds the prompt from these."""
        return {
            "candidate_kind": self.candidate_kind,
            "card_language": self.card_language,
            "place_and_time": self.place_and_time,
            "conversation": "\n".join(self.conversation) or NOTHING_BEFORE,
            "candidate": self.candidate,
        }

    def text(self) -> str:
        return self.prompt.render(self.values())

    def event(self) -> dict[str, Any]:
        """For the recording: the prompt's name and version, the values filled
        in, and the place each search tool was told. Never the rendered text."""
        return {
            "prompt": self.prompt.name, "version": self.prompt.version, "values": self.values(),
            "openai_location": openai_location(self.openai_location),
            "perplexity_location": perplexity_location(self.perplexity_location),
        }


@dataclass(frozen=True)
class DraftCard:
    """A fact card as a fact-finder wrote it, never shown as it is: the title
    and one-sentence fact in the card language, the source's URL and title,
    and a passage the fact-finder says it copied word for word from the
    source, in the source's own language."""

    title: str
    fact: str
    source_url: str
    source_title: str
    excerpt: str


@dataclass(frozen=True)
class SearchResult:
    """One search result as the provider gave it. OpenAI's have no snippet,
    and a title only when it gives one."""

    url: str
    title: str = ""
    snippet: str = ""


@dataclass(frozen=True)
class Finding:
    """What a fact-finder found for one candidate.

    - `outcome`: `claim is wrong`, `claim is right`, `question answered` or
      `not found`. `restatement`: the candidate as one standalone sentence,
      for every outcome.
    - `card`: the draft card, complete, for `claim is wrong` and `question
      answered` only; None otherwise.
    - `results`: every search result, as given, repeats included.
      `searches`: the queries searched. `search_calls`: the searches charged,
      which for Perplexity can each run several queries.
    - `model`: the model the provider reports it ran (as in the record);
      `model_differs` is true when that isn't the pinned one.
    """

    outcome: str
    restatement: str
    card: DraftCard | None
    results: tuple[SearchResult, ...]
    searches: tuple[str, ...]
    search_calls: int
    model: str
    model_differs: bool
    record: CallRecord

    @property
    def source_in_results(self) -> bool | None:
        """Whether the card's source is among the search results; None without a card."""
        if self.card is None:
            return None
        return any(same_url(r.url, self.card.source_url) for r in self.results)

    def event(self) -> dict[str, Any]:
        """The finding as a JSON-ready dict for the recording, without its record."""
        return {
            "outcome": self.outcome, "restatement": self.restatement,
            "card": None if self.card is None else asdict(self.card),
            "results": [asdict(r) for r in self.results], "searches": list(self.searches),
            "search_calls": self.search_calls, "model": self.model, "model_differs": self.model_differs,
            "source_in_results": self.source_in_results,
        }


class FactFinder(Protocol):
    async def find(self, request: FindingRequest, *, stage: str) -> Finding:
        """Search for one candidate and write its draft card. `stage` names
        the call in the record and the failure log: `fact-finding A` or
        `fact-finding B` (STAGE_A, STAGE_B).

        Raises ModelError on failure, with the call's record. Never retries.
        """


def same_url(a: str, b: str) -> bool:
    """The same page: the scheme, a `www.`, a trailing slash, percent-encoding
    and the fragment aside."""

    def key(url: str) -> tuple[str, str, str]:
        parts = urlsplit(url.strip())
        return parts.netloc.lower().removeprefix("www."), unquote(parts.path).rstrip("/"), parts.query

    return key(a) == key(b)


def same_model(pinned: str, reported: str) -> bool:
    """Whether the model a provider reports is the pinned one. It may drop
    the vendor prefix or add a dated suffix: `google/gemini-3.8-flash` and
    `gemini-3.8-flash`, `gpt-6-luna` and `gpt-6-luna-2026-09-01`."""

    def name(model: str) -> str:
        return DATED.sub("", model.strip().rsplit("/", 1)[-1]).lower()

    return name(pinned) == name(reported)


class BadOutput(Exception):
    pass


def parse(text: str) -> tuple[str, str, DraftCard | None]:
    """The outcome, the restatement and the card from a fact-finder's JSON.

    Raises BadOutput for anything but a JSON object with a known outcome and
    a restatement, and for `claim is wrong` or `question answered` without a
    complete card: every field filled in and a web address as the source.
    The card fields of the other outcomes are ignored.
    """
    try:
        answer = json.loads(FENCE.sub("", text.strip()))
    except ValueError:
        raise BadOutput(f"not JSON: {text}") from None
    if not isinstance(answer, dict):
        raise BadOutput(f"not a JSON object: {text}")
    outcome = answer.get("outcome")
    if not isinstance(outcome, str) or outcome not in OUTCOMES:
        raise BadOutput(f"outcome {outcome!r} is not one of {', '.join(OUTCOMES)}: {text}")
    restatement = answer.get("restatement")
    if not isinstance(restatement, str) or not restatement.strip():
        raise BadOutput(f"no restatement: {text}")
    if outcome not in CARD_OUTCOMES:
        return outcome, restatement.strip(), None
    missing = [k for k in CARD_FIELDS if not isinstance(answer.get(k), str) or not answer[k].strip()]
    if missing:
        raise BadOutput(f"{outcome} with an incomplete card, no {', '.join(missing)}: {text}")
    card = DraftCard(**{k: answer[k].strip() for k in CARD_FIELDS})
    parts = urlsplit(card.source_url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise BadOutput(f"source_url {card.source_url!r} is not a web address: {text}")
    return outcome, restatement.strip(), card


def count(value: Any) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0


def table(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def message(item: dict[str, Any]) -> tuple[str, str | None]:
    """A `message` output item's text, and its refusal if it has one."""
    text, refusal = "", None
    for part in item.get("content") or []:
        if part.get("type") == "output_text":
            text += str(part.get("text") or "")
        elif part.get("type") == "refusal":
            refusal = str(part.get("refusal"))
    return text, refusal


@dataclass
class Output:
    """What an adapter reads from a response's output items."""

    text: str = ""
    refusal: str | None = None
    searches: list[str] = field(default_factory=list)
    results: list[SearchResult] = field(default_factory=list)
    search_calls: int = 0


class Finder(HttpAdapter):
    """What both fact-finders share: the call, its checks and its cost.

    A subclass builds the request body (`body`) and reads the searches,
    results and answer text from the response (`read`).
    """

    typical_searches: ClassVar[int]

    def __init__(
        self,
        stage: Stage,
        price: Price,
        key: str,
        session: aiohttp.ClientSession,
        *,
        timeout_s: float = FINDING_TIMEOUT_S,
        base_url: str | None = None,
    ) -> None:
        super().__init__(stage, price, key, session, timeout_s=timeout_s, base_url=base_url)
        if price.search is None:
            raise ValueError(f"{self.provider} {stage.model}: the price table needs a search price")
        self.search_price = price.search

    def body(self, request: FindingRequest) -> dict[str, Any]:
        raise NotImplementedError

    def read(self, body: dict[str, Any]) -> Output:
        raise NotImplementedError

    def provider_cost(self, usage: dict[str, Any]) -> float | None:
        return None

    async def find(self, request: FindingRequest, *, stage: str) -> Finding:
        record = CallRecord(
            stage, self.provider, self.stage.model, request.prompt.name, request.prompt.version,
            request.values(), dict(self.stage.params), request=self.body(request),
        )
        body = await self.post(record)
        record.model = str(body.get("model") or record.model)
        try:
            out = self.read(body)
        except (AttributeError, KeyError, TypeError, ValueError) as e:
            self.bill(record, body, None)
            raise self.fail(record, "bad output", f"can't read the output ({e!r}): {json.dumps(body)}") from None
        self.bill(record, body, out.search_calls)
        # A 200 can still carry a run that failed or stopped short.
        status = body.get("status")
        if status == "failed":
            raise self.fail(record, "unavailable", f"status failed: {json.dumps(body.get('error'))}")
        if status not in (None, "completed"):
            details = body.get("incomplete_details") or body.get("error")
            raise self.fail(record, "bad output", f"status {status}: {json.dumps(details)}")
        if out.refusal is not None:
            raise self.fail(record, "bad output", f"refusal: {out.refusal}")
        try:
            outcome, restatement, card = parse(out.text)
        except BadOutput as e:
            raise self.fail(record, "bad output", str(e)) from None
        differs = not same_model(self.stage.model, record.model)
        if differs:
            log.warning("%s via %s: ran %s, not the pinned %s", stage, self.provider, record.model, self.stage.model)
        return Finding(outcome, restatement, card, tuple(out.results), tuple(out.searches), out.search_calls,
                       record.model, differs, record)

    def bill(self, record: CallRecord, body: dict[str, Any], searches: int | None) -> None:
        """Tokens at the price table's rates plus the searches at the search
        price. The typical number of searches stands in, marked estimated,
        when the output can't be read."""
        usage = body.get("usage")
        if not isinstance(usage, dict) or not usage:
            self.estimate(record, searches)
            return
        details = table(usage.get("input_tokens_details"))
        self.charge(record, count(usage.get("input_tokens")), count(details.get("cached_tokens")),
                    count(usage.get("output_tokens")), self.provider_cost(usage))
        if searches is None:
            searches, record.estimated = self.typical_searches, True
        record.cost_usd += searches * self.search_price
        if record.provider_cost_usd is not None and abs(record.provider_cost_usd - record.cost_usd) >= 1e-6:
            log.info("%s via %s: the provider charged $%.6f, the price table says $%.6f (%+.6f)", record.stage,
                     self.provider, record.provider_cost_usd, record.cost_usd,
                     record.provider_cost_usd - record.cost_usd)

    def estimate(self, record: CallRecord, searches: int | None = None) -> None:
        """An estimate for a call whose usage is unknown: the tokens Carl sent
        and the typical output, plus the typical number of searches unless
        the output said how many ran. A request refused with a 4xx ran no
        search, so it is charged none."""
        super().estimate(record)
        if searches is None:
            refused = record.status is not None and 400 <= record.status < 500
            searches = 0 if refused else self.typical_searches
        record.cost_usd += searches * self.search_price


class OpenAIFinder(Finder):
    """Fact-finder A: an OpenAI model with OpenAI's `web_search` on the
    Responses API, and a strict JSON schema for the draft card.

    The stage's parameters set the reasoning effort, `tool_choice` (search
    is forced with `required`, the default), the search context size and the
    most output tokens.
    """

    provider = "openai"
    key_name = "OPENAI_API_KEY"
    default_base_url = "https://api.openai.com/v1"
    path = "/responses"
    known_params = frozenset({"reasoning_effort", "tool_choice", "search_context_size", "max_output_tokens"})
    # Luna's draft cards came to 123-257 output tokens, with one search each
    # (steps 0 and 4).
    typical_output_tokens = 300
    typical_searches = 1

    def body(self, request: FindingRequest) -> dict[str, Any]:
        params = self.stage.params
        tool: dict[str, Any] = {"type": "web_search"}
        if (where := openai_location(request.openai_location)) is not None:
            tool["user_location"] = where
        if "search_context_size" in params:
            tool["search_context_size"] = params["search_context_size"]
        body: dict[str, Any] = {
            "model": self.stage.model,
            "store": False,
            "tools": [tool],
            "tool_choice": params.get("tool_choice", "required"),
            "include": ["web_search_call.action.sources"],
            "input": request.text(),
            "text": {"format": {"type": "json_schema", "name": SCHEMA_NAME, "strict": True, "schema": SCHEMA}},
        }
        if "reasoning_effort" in params:
            body["reasoning"] = {"effort": params["reasoning_effort"]}
        if "max_output_tokens" in params:
            body["max_output_tokens"] = params["max_output_tokens"]
        return body

    def read(self, body: dict[str, Any]) -> Output:
        """Each `web_search_call` of type `search` is a search, and its
        `action.sources` are results. With reasoning on, a call can also open
        a page or search within one; those are neither searches nor charged."""
        out = Output()
        for item in body.get("output") or []:
            if item.get("type") == "web_search_call":
                action = table(item.get("action"))
                if action.get("type", "search") != "search":
                    continue
                out.search_calls += 1
                out.searches.append(str(action.get("query") or "; ".join(map(str, action.get("queries") or []))))
                out.results += [
                    SearchResult(str(s["url"]), str(s.get("title") or ""))
                    for s in action.get("sources") or [] if isinstance(s, dict) and s.get("url")
                ]
            elif item.get("type") == "message":
                out.text, out.refusal = message(item)  # the last message is the answer
        return out


class PerplexityFinder(Finder):
    """Fact-finder B: a model pinned on Perplexity's Agent API, with its
    `web_search` and a strict JSON schema for the draft card.

    The stage's parameters set the reasoning effort, the search type and
    context size, the most agent steps and the most output tokens. The
    model is pinned so that no preset can change it under Carl; the model
    the response reports is recorded, and a different one is flagged.
    """

    provider = "perplexity"
    key_name = "PERPLEXITY_API_KEY"
    default_base_url = "https://api.perplexity.ai/v1"
    path = "/agent"
    known_params = frozenset(
        {"reasoning_effort", "search_type", "search_context_size", "max_steps", "max_output_tokens"}
    )
    # Gemini's draft cards came to 163-270 output tokens, each after one
    # `search_web` invocation that ran two queries (steps 0 and 4).
    typical_output_tokens = 300
    typical_searches = 1

    def body(self, request: FindingRequest) -> dict[str, Any]:
        params = self.stage.params
        tool: dict[str, Any] = {"type": "web_search"}
        for name in ("search_type", "search_context_size"):
            if name in params:
                tool[name] = params[name]
        if (where := perplexity_location(request.perplexity_location)) is not None:
            tool["user_location"] = where
        body: dict[str, Any] = {
            "model": self.stage.model,
            "store": False,
            "input": request.text(),
            "tools": [tool],
            "response_format": {
                "type": "json_schema", "json_schema": {"name": SCHEMA_NAME, "strict": True, "schema": SCHEMA},
            },
        }
        if "reasoning_effort" in params:
            body["reasoning"] = {"effort": params["reasoning_effort"]}
        for name in ("max_steps", "max_output_tokens"):
            if name in params:
                body[name] = params[name]
        return body

    def read(self, body: dict[str, Any]) -> Output:
        """Each `search_results` item is one search, which can run several
        queries, and its results are results. The searches charged are the
        usage's `search_web` invocations, or the items when it doesn't say."""
        out, items = Output(), 0
        for item in body.get("output") or []:
            if item.get("type") == "search_results":
                items += 1
                out.searches += [str(q) for q in item.get("queries") or []] or ["(no query given)"]
                out.results += [
                    SearchResult(str(r["url"]), str(r.get("title") or ""), str(r.get("snippet") or ""))
                    for r in item.get("results") or [] if isinstance(r, dict) and r.get("url")
                ]
            elif item.get("type") == "message":
                out.text, out.refusal = message(item)  # the last message is the answer
        usage = table(body.get("usage"))
        invocations = table(table(usage.get("tool_calls_details")).get("search_web")).get("invocation")
        out.search_calls = invocations if isinstance(invocations, int) and invocations >= 0 else items
        return out

    def provider_cost(self, usage: dict[str, Any]) -> float | None:
        """Perplexity's own figure: `usage.cost.total_cost`."""
        cost = usage.get("cost")
        if isinstance(cost, dict):
            cost = cost.get("total_cost")
        return float(cost) if isinstance(cost, int | float) and not isinstance(cost, bool) else None


ADAPTERS: dict[str, type[Finder]] = {"openai": OpenAIFinder, "perplexity": PerplexityFinder}


def key_name(stage: Stage) -> str:
    """The secret that holds the stage's key. Raises ValueError for an unknown provider."""
    if stage.provider not in ADAPTERS:
        raise ValueError(f"no fact-finding adapter for provider {stage.provider!r}")
    return ADAPTERS[stage.provider].key_name


def make_fact_finder(
    stage: Stage,
    config: Config,
    secrets: Mapping[str, str],
    session: aiohttp.ClientSession,
    *,
    timeout_s: float = FINDING_TIMEOUT_S,
    base_url: str | None = None,
) -> FactFinder:
    """The adapter the config file selects for `stage` (`stages.fact_finder_a`
    or `stages.fact_finder_b`), with its key from `secrets` and its prices,
    the search price included, from the config's price table.

    `base_url` points the adapter somewhere else, such as a test's fake
    server. Raises ValueError for an unknown provider, an unknown parameter,
    a missing price or a missing key.
    """
    name = key_name(stage)
    key = secrets.get(name)
    if not key:
        raise ValueError(f"{name} is not set")
    return ADAPTERS[stage.provider](stage, config.price(stage), key, session, timeout_s=timeout_s, base_url=base_url)
