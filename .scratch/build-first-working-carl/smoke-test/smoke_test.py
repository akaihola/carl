#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx[http2]>=0.27"]
# ///
"""Carl build step 0: the provider smoke test.

Calls each text stage's provisional model, and on request its fallback, with
the Finnish and English cases in cases.toml, and reports whether each does
what the First working Carl spec needs from it. See README.md.

This is a local, throwaway script. Nothing in Carl imports it.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import math
import os
import re
import statistics
import time
import tomllib
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit
from zoneinfo import ZoneInfo

import httpx

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
PROMPTS = HERE / "prompts"

OPENAI_URL = "https://api.openai.com/v1/responses"
PERPLEXITY_URL = "https://api.perplexity.ai/v1/agent"
TYPESAFE_URL = "https://api.typesafe.ai/v1/systemone"
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

KEY_NAMES = {
    "openai": "OPENAI_API_KEY",
    "perplexity": "PERPLEXITY_API_KEY",
    "typesafe": "TYPESAFE_API_KEY",
    "gemini": "GEMINI_API_KEY",
}

# USD per 1M tokens, from the vendors' pricing pages on 2026-09-26.
PRICES = {
    "gpt-6-luna": {"input": 0.10, "cached": 0.01, "output": 0.50},
    "openai/gpt-6-luna": {"input": 0.10, "cached": 0.10, "output": 0.50},
    "google/gemini-3.8-flash": {"input": 0.75, "cached": 0.075, "output": 3.75},
    "gemini-3.5-flash-lite": {"input": 0.30, "cached": 0.03, "output": 2.50},
    "jev-1.13.0": {"input": 0.042, "cached": 0.0, "output": 0.0},
}
# USD per search call.
SEARCH_PRICES = {"openai": 10.00 / 1000, "perplexity-web": 2.50 / 1000, "perplexity-fast": 1.00 / 1000}

# A first draft of the config file's blocklist (spec section 6): forums and
# Q&A sites, social media, video platforms, user-edited wikis other than
# Wikipedia. Matched as domain suffixes.
BLOCKLIST = [
    "reddit.com", "quora.com", "stackexchange.com", "stackoverflow.com",
    "suomi24.fi", "vauva.fi", "ylilauta.org",
    "facebook.com", "instagram.com", "x.com", "twitter.com", "threads.net",
    "tiktok.com", "linkedin.com", "pinterest.com",
    "youtube.com", "youtu.be", "vimeo.com", "twitch.tv",
    "fandom.com", "wikia.org",
]

FINDING_OUTCOMES = ["claim is wrong", "claim is right", "question answered", "not found"]
FINDING_SCHEMA = {
    "type": "object",
    "properties": {
        "restatement": {"type": "string"},
        "outcome": {"type": "string", "enum": FINDING_OUTCOMES},
        "title": {"type": "string"},
        "fact": {"type": "string"},
        "source_url": {"type": "string"},
        "source_title": {"type": "string"},
        "excerpt": {"type": "string"},
    },
    "required": ["restatement", "outcome", "title", "fact", "source_url", "source_title", "excerpt"],
    "additionalProperties": False,
}

TYPED_TIMEOUT_S = 60.0
FINDING_TIMEOUT_S = 120.0  # Perplexity: a new JSON schema can take 10-30 s to prepare
SPEC_DOWNLOAD_TIMEOUT_S = 3.0  # spec section 6, fact-finder A's page download
DOWNLOAD_TIMEOUT_S = 10.0  # longer here, to see how much the 3 s limit loses


# --- Secrets, prompts, cases -------------------------------------------------


def load_secrets() -> None:
    """Read KEY=VALUE lines from the gitignored .secrets.* files at the repo root.

    Variables already set in the environment win.
    """
    for path in sorted(REPO_ROOT.glob(".secrets.*")):
        if not path.is_file():
            continue
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            name, value = line.removeprefix("export ").split("=", 1)
            os.environ.setdefault(name.strip(), value.strip().strip("'\""))


def sections(text: str) -> dict[str, str]:
    """Split a prompt file into its '# Heading' sections."""
    parts: dict[str, str] = {}
    current = None
    for line in text.splitlines():
        if line.startswith("# "):
            current = line[2:].strip().lower()
            parts[current] = ""
        elif current is not None:
            parts[current] += line + "\n"
    return {name: body.strip() for name, body in parts.items()}


@dataclass
class TypedPrompt:
    """A typed-answer prompt: one question and a description for each choice."""

    name: str
    question: str
    choices: dict[str, str]

    @classmethod
    def load(cls, name: str, candidate_ids: list[str] | None = None) -> TypedPrompt:
        text = (PROMPTS / f"{name}.md").read_text()
        parts = sections(text)
        choices: dict[str, str] = {}
        for item in re.split(r"\n(?=- `)", parts["choices"]):
            m = re.match(r"- `([^`]+)`:\s*(.*)", item, re.S)
            if not m:
                raise SystemExit(f"prompts/{name}.md: can't read choice {item!r}")
            choice, description = m.group(1), " ".join(m.group(2).split())
            if "Cn" in choice:
                # One choice per earlier candidate: `same as Cn` → `same as C1`…
                for cid in candidate_ids or []:
                    choices[choice.replace("Cn", cid)] = description.replace("Cn", cid)
            else:
                choices[choice] = description
        question = " ".join(parts["question"].split())
        return cls(name, question, choices)


def prompt_versions() -> str:
    """Each prompt file's version, a short hash of its content (spec section 7)."""
    return ", ".join(
        f"{path.stem} {hashlib.sha256(path.read_bytes()).hexdigest()[:8]}" for path in sorted(PROMPTS.glob("*.md"))
    )


def render(name: str, values: dict[str, str]) -> str:
    """Fill a prompt template's {placeholders}. Fail on any left unfilled."""
    text = (PROMPTS / f"{name}.md").read_text()
    missing = sorted({m for m in re.findall(r"\{([a-z_]+)\}", text) if m not in values})
    if missing:
        raise SystemExit(f"prompts/{name}.md: nothing fills {', '.join(missing)}")
    return re.sub(r"\{([a-z_]+)\}", lambda m: values[m.group(1)], text)


@dataclass
class Place:
    neighbourhood: str
    city: str
    region: str
    country: str
    country_name: str
    timezone: str

    def date_time(self) -> str:
        now = datetime.now(ZoneInfo(self.timezone))
        return f"{now:%A} {now.day} {now:%B %Y, %H:%M} ({self.timezone})"

    def place_and_time(self) -> str:
        return f"{self.neighbourhood}, {self.city}, {self.country_name}. {self.date_time()}"


def split_conversation(lines: list[str]) -> tuple[str, str]:
    """The lines said before, and the last line (the one judged or checked)."""
    before = "\n".join(lines[:-1]) or "(nothing said before)"
    return before, lines[-1]


# --- Calls -------------------------------------------------------------------


@dataclass
class Call:
    """One HTTP call to a provider, with what came back."""

    status: int | None = None
    elapsed_s: float = 0.0
    body: dict | None = None
    error: str | None = None  # timeout / unavailable / rate-limited / rejected / bad output
    error_detail: str = ""


class Recorder:
    """Writes each call's request and response to the output folder.

    Headers are never written, so the keys stay out of it.
    """

    def __init__(self, out_dir: Path):
        self.out_dir = out_dir
        out_dir.mkdir(parents=True, exist_ok=True)

    def save(self, check: str, case: str, request: dict, call: Call) -> None:
        path = self.out_dir / check / f"{case}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "request": request,
            "status": call.status,
            "elapsed_s": round(call.elapsed_s, 3),
            "error": call.error,
            "error_detail": call.error_detail,
            "response": call.body,
        }
        path.write_text(json.dumps(record, ensure_ascii=False, indent=2))


def post(client: httpx.Client, url: str, headers: dict, body: dict, timeout: float) -> Call:
    call = Call()
    start = time.perf_counter()
    try:
        response = client.post(url, headers=headers, json=body, timeout=timeout)
    except httpx.TimeoutException as e:
        call.error, call.error_detail = "timeout", repr(e)
    except httpx.TransportError as e:
        call.error, call.error_detail = "unavailable", repr(e)
    else:
        call.status = response.status_code
        try:
            call.body = response.json()
        except ValueError:
            call.body = {"raw_text": response.text[:4000]}
        if response.status_code == 429:
            call.error = "rate-limited"
        elif response.status_code >= 500:
            call.error = "unavailable"
        elif response.status_code >= 400:
            call.error = "rejected"
        if call.error:
            call.error_detail = f"HTTP {response.status_code}: {json.dumps(call.body, ensure_ascii=False)[:600]}"
    call.elapsed_s = time.perf_counter() - start
    return call


def failed_run(call: Call) -> bool:
    """A 200 response can still carry a failed or incomplete run."""
    status = call.body.get("status")
    if status in (None, "completed"):
        return False
    call.error = "unavailable" if status == "failed" else "bad output"
    details = call.body.get("error") or call.body.get("incomplete_details")
    call.error_detail = f"status {status}: {json.dumps(details, ensure_ascii=False)}"
    return True


def token_cost(model: str, input_tokens: int, cached_tokens: int, output_tokens: int) -> float | None:
    price = PRICES.get(model)
    if price is None:
        return None
    return (
        (input_tokens - cached_tokens) * price["input"]
        + cached_tokens * price["cached"]
        + output_tokens * price["output"]
    ) / 1_000_000


# --- Typed answers: decision model and fact-checking model --------------------


@dataclass
class TypedResult:
    answer: str | None = None
    probs: dict[str, float] | None = None  # None: the provider gave none
    probs_note: str = ""
    cost: float | None = None
    model: str = ""
    call: Call = field(default_factory=Call)


def answer_schema(choices: list[str]) -> dict:
    return {
        "type": "object",
        "properties": {"answer": {"type": "string", "enum": choices}},
        "required": ["answer"],
        "additionalProperties": False,
    }


def llm_messages(prompt: TypedPrompt, fields: dict[str, str]) -> tuple[str, str]:
    """How the LLM adapters present a typed call: the question, then the fields."""
    choices = "\n".join(f"- `{c}`: {d}" for c, d in prompt.choices.items())
    system = (
        f"{prompt.question}\n\nAnswer with JSON: {{\"answer\": one of the choices below, "
        f"written exactly as given}}.\n\nChoices:\n{choices}"
    )
    user = "\n\n".join(f"`{name}`:\n{value}" for name, value in fields.items())
    return system, user


def first_token_probs(steps: list[tuple[str, float, list[tuple[str, float]]]], choices: list[str]) -> dict[str, float] | None:
    """Each choice's probability, read from the logprobs of the answer's first token.

    `steps` holds (token, logprob, [(alternative, logprob)…]) per output token.
    Choices that share their first token can't be told apart this way: all
    `same as Cn` choices are pooled as `same as *` (the repeat rule adds them
    up anyway), and any other overlap is counted as `ambiguous`. Mass outside
    the returned alternatives is `other`.
    """
    joined, starts = "", []
    for token, _, _ in steps:
        starts.append(len(joined))
        joined += token
    m = re.search(r'"answer"\s*:\s*"', joined)
    if not m:
        return None
    value_start = m.end()
    for i, (token, _, _) in enumerate(steps):
        if starts[i] <= value_start < starts[i] + len(token):
            break
    else:
        return None
    prefix = joined[starts[i]:value_start]
    token, logprob, alternatives = steps[i]
    seen: dict[str, float] = {}
    for alt, alt_logprob in [(token, logprob), *alternatives]:
        seen.setdefault(alt, alt_logprob)

    def key(alt: str) -> str:
        if not alt.startswith(prefix):
            return "other"
        rest = alt[len(prefix):]
        if '"' in rest:
            matches = [c for c in choices if c == rest.split('"', 1)[0]]
        else:
            matches = [c for c in choices if c.startswith(rest)] if rest else list(choices)
        if len(matches) == 1:
            return matches[0]
        if matches and all(c.startswith("same as ") for c in matches):
            return "same as *"
        return "ambiguous" if matches else "other"

    probs: dict[str, float] = {}
    for alt, alt_logprob in seen.items():
        k = key(alt)
        probs[k] = probs.get(k, 0.0) + math.exp(alt_logprob)
    covered = sum(probs.values())
    if covered < 1:
        probs["other"] = probs.get("other", 0.0) + (1 - covered)
    return probs


def typed_openai(client, key, model, prompt: TypedPrompt, fields, recorder, check, case) -> TypedResult:
    system, user = llm_messages(prompt, fields)
    body = {
        "model": model,
        "reasoning": {"effort": "none"},
        "store": False,
        "input": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "text": {"format": {"type": "json_schema", "name": "typed_answer", "strict": True,
                            "schema": answer_schema(list(prompt.choices))}},
        "include": ["message.output_text.logprobs"],
        "top_logprobs": 20,
        "max_output_tokens": 200,
    }
    result = TypedResult(model=model)
    call = post(client, OPENAI_URL, {"Authorization": f"Bearer {key}"}, body, TYPED_TIMEOUT_S)
    recorder.save(check, case, body, call)
    result.call = call
    if call.error or failed_run(call):
        return result
    text, steps = "", []
    for item in call.body.get("output", []):
        if item.get("type") != "message":
            continue
        for part in item.get("content", []):
            if part.get("type") == "output_text":
                text += part.get("text", "")
                for lp in part.get("logprobs") or []:
                    alts = [(a["token"], a["logprob"]) for a in lp.get("top_logprobs", [])]
                    steps.append((lp["token"], lp["logprob"], alts))
    result.answer = parse_answer(text, prompt, call)
    if steps:
        result.probs = first_token_probs(steps, list(prompt.choices))
        if result.probs is None:
            result.probs_note = "logprobs came back but the answer token wasn't found in them"
    else:
        result.probs_note = "no logprobs in the response"
    usage = call.body.get("usage") or {}
    result.cost = token_cost(
        model, usage.get("input_tokens", 0),
        (usage.get("input_tokens_details") or {}).get("cached_tokens", 0),
        usage.get("output_tokens", 0),
    )
    return result


def typed_gemini(client, key, model, prompt: TypedPrompt, fields, recorder, check, case) -> TypedResult:
    system, user = llm_messages(prompt, fields)
    schema = answer_schema(list(prompt.choices))
    base = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": user}]}],
    }
    config = {"responseLogprobs": True, "logprobs": 20, "thinkingConfig": {"thinkingLevel": "MINIMAL"},
              "maxOutputTokens": 2048}
    # The docs disagree on how to ask for a schema. Try the current field
    # first, then the two older ones, and report which one worked.
    variants = [
        ("responseFormat", {"responseFormat": {"text": {"mimeType": "application/json", "schema": schema}}}),
        ("responseJsonSchema", {"responseMimeType": "application/json", "responseJsonSchema": schema}),
        ("responseSchema", {"responseMimeType": "application/json", "responseSchema": schema}),
    ]
    result = TypedResult(model=model)
    for variant, schema_config in variants:
        body = base | {"generationConfig": config | schema_config}
        call = post(client, GEMINI_URL.format(model=model), {"x-goog-api-key": key}, body, TYPED_TIMEOUT_S)
        if call.status != 400:
            break
    recorder.save(check, case, body, call)
    result.call = call
    if call.error:
        return result
    candidate = (call.body.get("candidates") or [{}])[0]
    parts = (candidate.get("content") or {}).get("parts") or []
    text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
    result.answer = parse_answer(text, prompt, call)
    notes = [f"schema via {variant}"]
    logprobs = candidate.get("logprobsResult") or {}
    chosen, top = logprobs.get("chosenCandidates") or [], logprobs.get("topCandidates") or []
    if chosen:
        steps = []
        for i, c in enumerate(chosen):
            alts = [(a["token"], a["logProbability"]) for a in (top[i].get("candidates", []) if i < len(top) else [])]
            steps.append((c["token"], c["logProbability"], alts))
        result.probs = first_token_probs(steps, list(prompt.choices))
        if result.probs is None:
            notes.append("logprobs came back but the answer token wasn't found in them")
    else:
        notes.append("no logprobs in the response")
    result.probs_note = "; ".join(notes)
    usage = call.body.get("usageMetadata") or {}
    result.model = call.body.get("modelVersion", model)
    result.cost = token_cost(
        model, usage.get("promptTokenCount", 0), usage.get("cachedContentTokenCount", 0),
        usage.get("candidatesTokenCount", 0) + usage.get("thoughtsTokenCount", 0),
    )
    return result


def typed_jev(client, key, model, prompt: TypedPrompt, fields, recorder, check, case) -> TypedResult:
    body = {
        "model": model,
        "state": fields,
        "questions": {
            "answer": {"type": "choice", "instructions": prompt.question, "criteria": prompt.choices},
        },
    }
    result = TypedResult(model=model)
    call = post(client, TYPESAFE_URL, {"Authorization": f"Bearer {key}"}, body, TYPED_TIMEOUT_S)
    recorder.save(check, case, body, call)
    result.call = call
    if call.error:
        return result
    answer = (call.body.get("answers") or {}).get("answer") or {}
    result.model = call.body.get("model", model)
    result.answer = answer.get("choice")
    if result.answer not in prompt.choices:
        call.error, call.error_detail = "bad output", f"choice {result.answer!r} is not one of the choices"
    result.probs = answer.get("probabilities")
    if result.probs is None:
        result.probs_note = "no probabilities in the response"
    elif "confidence" in answer:
        result.probs_note = f"Jev confidence {answer['confidence']:.2f}"
    usage = call.body.get("usage") or {}
    result.cost = token_cost(model, usage.get("input_tokens", 0), 0, usage.get("output_tokens", 0))
    return result


def parse_answer(text: str, prompt: TypedPrompt, call: Call) -> str | None:
    try:
        answer = json.loads(text)["answer"]
    except (ValueError, KeyError, TypeError):
        call.error, call.error_detail = "bad output", f"not the expected JSON: {text[:300]!r}"
        return None
    if answer not in prompt.choices:
        call.error, call.error_detail = "bad output", f"answer {answer!r} is not one of the choices"
        return None
    return answer


# --- Fact-finding models -------------------------------------------------------


@dataclass
class Finding:
    card: dict | None = None  # the parsed JSON: restatement, outcome, draft card
    model: str = ""  # the model the provider reports it ran
    searches: list[str] = field(default_factory=list)  # queries, one per search
    results: list[dict] = field(default_factory=list)  # {url, title, snippet} where the provider gives them
    citations: list[str] = field(default_factory=list)  # url_citation URLs
    cost: float | None = None  # Carl's figure from the price table
    provider_cost: float | None = None  # the provider's own figure, when it gives one
    call: Call = field(default_factory=Call)


def finding_openai(client, key, model, prompt_text, place: Place, recorder, check, case) -> Finding:
    body = {
        "model": model,
        "reasoning": {"effort": "none"},
        "store": False,
        "tools": [{
            "type": "web_search",
            "user_location": {"type": "approximate", "city": place.city, "region": place.region,
                              "country": place.country, "timezone": place.timezone},
        }],
        "tool_choice": "required",
        "include": ["web_search_call.action.sources"],
        "input": prompt_text,
        "text": {"format": {"type": "json_schema", "name": "draft_card", "strict": True, "schema": FINDING_SCHEMA}},
    }
    finding = Finding(model=model)
    call = post(client, OPENAI_URL, {"Authorization": f"Bearer {key}"}, body, FINDING_TIMEOUT_S)
    recorder.save(check, case, body, call)
    finding.call = call
    if call.error or failed_run(call):
        return finding
    finding.model = call.body.get("model", model)
    text = ""
    for item in call.body.get("output", []):
        if item.get("type") == "web_search_call":
            action = item.get("action") or {}
            if action.get("type") == "search":
                finding.searches.append(action.get("query") or "; ".join(action.get("queries") or []))
                finding.results += [{"url": s["url"]} for s in action.get("sources") or [] if s.get("url")]
        elif item.get("type") == "message":
            for part in item.get("content", []):
                if part.get("type") == "output_text":
                    text += part.get("text", "")
                    finding.citations += [a["url"] for a in part.get("annotations", []) if a.get("url")]
                elif part.get("type") == "refusal":
                    call.error, call.error_detail = "bad output", f"refusal: {part.get('refusal')}"
    finding.card = parse_card(text, call)
    usage = call.body.get("usage") or {}
    tokens = token_cost(
        model, usage.get("input_tokens", 0),
        (usage.get("input_tokens_details") or {}).get("cached_tokens", 0), usage.get("output_tokens", 0),
    )
    finding.cost = None if tokens is None else tokens + len(finding.searches) * SEARCH_PRICES["openai"]
    return finding


def finding_perplexity(client, key, model, prompt_text, place: Place, recorder, check, case, opts) -> Finding:
    body = {
        "model": model,
        "input": prompt_text,
        "tools": [{
            "type": "web_search",
            "search_type": opts.pplx_search_type,
            "search_context_size": opts.pplx_search_context,
            "user_location": {"country": place.country, "region": place.region, "city": place.city},
        }],
        "response_format": {"type": "json_schema",
                            "json_schema": {"name": "draft_card", "strict": True, "schema": FINDING_SCHEMA}},
        "max_steps": opts.pplx_max_steps,
        "max_output_tokens": 4096,
        "store": False,
    }
    # Luna runs with reasoning off, as in fact-finder A. Gemini 3.8 Flash
    # rejects `minimal`, so it gets `low`.
    body["reasoning"] = {"effort": "none" if "luna" in model else "low"}
    finding = Finding(model=model)
    call = post(client, PERPLEXITY_URL, {"Authorization": f"Bearer {key}"}, body, FINDING_TIMEOUT_S)
    recorder.save(check, case, body, call)
    finding.call = call
    if call.error or failed_run(call):
        return finding
    finding.model = call.body.get("model", "")
    text = ""
    for item in call.body.get("output", []):
        if item.get("type") == "search_results":
            finding.searches += item.get("queries") or ["(no query given)"]
            finding.results += [
                {"url": r.get("url", ""), "title": r.get("title", ""), "snippet": r.get("snippet") or ""}
                for r in item.get("results") or []
            ]
        elif item.get("type") == "message":
            for part in item.get("content", []):
                if part.get("type") == "output_text":
                    text += part.get("text", "")
                    finding.citations += [a["url"] for a in part.get("annotations") or [] if a.get("url")]
    finding.card = parse_card(text, call)
    usage = call.body.get("usage") or {}
    details = usage.get("input_tokens_details") or {}
    searches = ((usage.get("tool_calls_details") or {}).get("search_web") or {}).get("invocation", 0)
    tokens = token_cost(model, usage.get("input_tokens", 0), details.get("cached_tokens", 0), usage.get("output_tokens", 0))
    per_search = SEARCH_PRICES[f"perplexity-{opts.pplx_search_type}"]
    finding.cost = None if tokens is None else tokens + searches * per_search
    finding.provider_cost = (usage.get("cost") or {}).get("total_cost")
    return finding


def parse_card(text: str, call: Call) -> dict | None:
    # Some models wrap JSON in a code fence despite the schema.
    stripped = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    try:
        card = json.loads(stripped)
    except ValueError:
        call.error, call.error_detail = "bad output", f"not JSON: {text[:300]!r}"
        return None
    missing = [k for k in FINDING_SCHEMA["required"] if not isinstance(card.get(k), str)]
    if missing or card["outcome"] not in FINDING_OUTCOMES:
        call.error, call.error_detail = "bad output", f"missing or wrong fields {missing or ['outcome']}: {text[:300]!r}"
        return None
    return card


# --- Excerpts and sources -------------------------------------------------------

QUOTES = str.maketrans({c: "'" for c in "‘’‚‛′`´"} | {c: '"' for c in "“”„‟″«»"})


def normalise(text: str) -> str:
    """Whitespace and quotation marks normalised, as the spec's excerpt match does."""
    return " ".join(unicodedata.normalize("NFKC", text).translate(QUOTES).split())


def same_url(a: str, b: str) -> bool:
    def key(url: str) -> tuple[str, str, str]:
        parts = urlsplit(url.strip())
        host = parts.netloc.lower().removeprefix("www.")
        return host, unquote(parts.path).rstrip("/"), parts.query

    return key(a) == key(b)


def blocklisted(url: str) -> str | None:
    host = urlsplit(url).hostname or ""
    for suffix in BLOCKLIST:
        if host == suffix or host.endswith("." + suffix):
            return suffix
    return None


def snippet_match(card: dict, results: list[dict]) -> str:
    """Fact-finder B's check: is the excerpt a substring of a snippet from the same URL?"""
    same = [r for r in results if r.get("snippet") and same_url(r["url"], card["source_url"])]
    if not same:
        return "url not in results" if results else "no search results"
    if any(card["excerpt"] in r["snippet"] for r in same):
        return "exact"
    if any(normalise(card["excerpt"]) in normalise(r["snippet"]) for r in same):
        return "normalised"
    return "no"


class _TextParser(HTMLParser):
    SKIP = {"script", "style", "noscript", "template"}
    BLOCK = {"p", "div", "br", "li", "ul", "ol", "dd", "dt", "td", "th", "tr", "table", "section",
             "article", "header", "footer", "blockquote", "figcaption", "h1", "h2", "h3", "h4", "h5", "h6"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skipping = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skipping += 1
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP:
            self.skipping = max(0, self.skipping - 1)
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skipping:
            self.parts.append(data)


def page_text(raw: str) -> str:
    """A page's visible text, for finding an excerpt in it.

    Inline tags add no space, so a word split by <b> or <a> stays whole.
    """
    parser = _TextParser()
    parser.feed(raw)
    return "".join(parser.parts)


def page_match(client: httpx.Client, card: dict) -> tuple[str, float]:
    """Fact-finder A's check: download the source and look for the excerpt."""
    start = time.perf_counter()
    try:
        response = client.get(
            card["source_url"], timeout=DOWNLOAD_TIMEOUT_S, follow_redirects=True,
            headers={"User-Agent": "Carl-smoke-test/0 (+https://github.com/akaihola/carl)"},
        )
    except httpx.HTTPError as e:
        return f"download failed ({type(e).__name__})", time.perf_counter() - start
    elapsed = time.perf_counter() - start
    if response.status_code != 200:
        return f"download failed (HTTP {response.status_code})", elapsed
    if "html" not in response.headers.get("content-type", "") and "text" not in response.headers.get("content-type", ""):
        return f"not a text page ({response.headers.get('content-type')})", elapsed
    return ("yes" if normalise(card["excerpt"]) in normalise(page_text(response.text)) else "no"), elapsed


# --- Checks ----------------------------------------------------------------------


@dataclass
class Check:
    name: str
    stage: str
    role: str  # provisional or fallback
    provider: str
    model: str
    kind: str  # decision / finding / checking

    @property
    def label(self) -> str:
        return f"{self.stage}: {self.model} via {self.provider} ({self.role})"


def all_checks(alt_models: list[str]) -> list[Check]:
    checks = [
        Check("decision-luna", "decision model", "provisional", "openai", "gpt-6-luna", "decision"),
        Check("finder-a-openai", "fact-finder A", "provisional", "openai", "gpt-6-luna", "finding"),
        Check("finder-b-perplexity", "fact-finder B", "provisional", "perplexity", "google/gemini-3.8-flash", "finding"),
        Check("checker-jev", "fact-checking model", "provisional", "typesafe", "jev-1.13.0", "checking"),
        Check("finder-a-perplexity", "fact-finder A", "fallback", "perplexity", "openai/gpt-6-luna", "finding"),
        Check("checker-gemini", "fact-checking model", "fallback", "gemini", "gemini-3.5-flash-lite", "checking"),
    ]
    for model in alt_models:
        slug = re.sub(r"[^a-z0-9]+", "-", model.lower()).strip("-")
        checks.append(Check(f"finder-b-{slug}", "fact-finder B", "fallback", "perplexity", model, "finding"))
    return checks


TYPED = {"openai": typed_openai, "gemini": typed_gemini, "typesafe": typed_jev}


@dataclass
class Row:
    """One case's outcome, for the summary."""

    case: str
    ok: bool  # the call came back and parsed
    as_expected: bool
    elapsed_s: float
    cost: float | None
    provider_cost: float | None = None
    probs: bool = False
    searched: bool = False
    card: bool = False  # the outcome carries a draft card
    complete: bool = False
    in_results: bool = False
    verified: bool = False
    model_as_pinned: bool = True
    error: str = ""


def fmt_probs(probs: dict[str, float] | None) -> str:
    if not probs:
        return "-"
    return ", ".join(f"{k} {v:.2f}" for k, v in sorted(probs.items(), key=lambda kv: -kv[1]) if v >= 0.005)


def decision_outcome(answer: str, probs: dict[str, float] | None) -> str:
    """Spec section 5: from probabilities to an outcome."""
    if not probs:
        return answer
    same = sum(v for k, v in probs.items() if k.startswith("same as "))
    if same >= 0.5:
        return answer if answer.startswith("same as ") else "same as *"
    claim, question = probs.get("claim", 0.0), probs.get("open question", 0.0)
    if claim + question >= 0.5:
        return "claim" if claim >= question else "open question"
    return "none"


def run_typed(check: Check, cases: list[dict], place: Place, env) -> list[Row]:
    rows = []
    for case in cases:
        if check.kind == "decision":
            ids = [c.split(":", 1)[0].strip() for c in case.get("earlier_candidates", [])]
            prompt = TypedPrompt.load("decision", ids)
            before, utterance = split_conversation(case["conversation"])
            fields = {
                "place_and_time": place.place_and_time(),
                "earlier_candidates": "\n".join(case.get("earlier_candidates", [])) or "(none yet)",
                "conversation": before,
                "utterance": utterance,
            }
        elif "card_1" in case:
            prompt = TypedPrompt.load("same-fact")
            fields = {"date_time": place.date_time(), "candidate": case["candidate"],
                      "card_1": case["card_1"], "card_2": case["card_2"]}
        else:
            prompt = TypedPrompt.load("fact-checking")
            before, candidate = split_conversation(case["conversation"])
            fields = {"date_time": place.date_time(), "conversation": before, "candidate": candidate}
            fields |= {k: case[k] for k in ("card_title", "card_fact", "source_title", "source_url", "excerpt")}
        r = TYPED[check.provider](env.client, env.key(check), check.model, prompt, fields, env.recorder, check.name, case["id"])
        call = r.call
        if call.error:
            rows.append(Row(case["id"], False, False, call.elapsed_s, None, error=f"{call.error}: {call.error_detail}"))
            print(f"  {case['id']:<26} ERROR {call.error}: {call.error_detail}")
            continue
        got = decision_outcome(r.answer, r.probs) if check.kind == "decision" else r.answer
        expected = case["expected"]
        match = got == expected or (got == "same as *" and expected.startswith("same as "))
        row = Row(case["id"], True, match, call.elapsed_s, r.cost, probs=bool(r.probs))
        rows.append(row)
        mark = "ok  " if match else "MISS"
        shown = got if got == r.answer else f"{got} (chose {r.answer})"
        print(f"  {case['id']:<26} {mark} {shown:<32} {call.elapsed_s:5.2f} s  {fmt_cost(r.cost)}")
        if not match:
            print(f"      expected: {expected}")
        print(f"      p: {fmt_probs(r.probs)}" + (f"   [{r.probs_note}]" if r.probs_note else ""))
    return rows


def run_finding(check: Check, cases: list[dict], place: Place, env) -> list[Row]:
    rows = []
    for case in cases:
        before, candidate = split_conversation(case["conversation"])
        prompt_text = render("fact-finding", {
            "candidate_kind": case["kind"],
            "card_language": case["card_language"],
            "place_and_time": place.place_and_time(),
            "conversation": before,
            "candidate": candidate,
        })
        if check.provider == "openai":
            f = finding_openai(env.client, env.key(check), check.model, prompt_text, place, env.recorder, check.name, case["id"])
        else:
            f = finding_perplexity(env.client, env.key(check), check.model, prompt_text, place, env.recorder, check.name, case["id"], env.opts)
        call = f.call
        if call.error:
            rows.append(Row(case["id"], False, False, call.elapsed_s, f.cost, f.provider_cost,
                            searched=bool(f.searches), error=f"{call.error}: {call.error_detail}"))
            print(f"  {case['id']:<26} ERROR {call.error}: {call.error_detail}")
            continue
        card = f.card
        outcome_ok = card["outcome"] == case["expected"]
        shows_card = card["outcome"] in ("claim is wrong", "question answered")
        want = case.get("expected_in_fact")
        fact_ok = not want or want.lower() in card["fact"].lower()
        row = Row(case["id"], True, outcome_ok and fact_ok, call.elapsed_s, f.cost, f.provider_cost,
                  searched=bool(f.searches), card=shows_card)
        # A reported model may carry a dated suffix, so compare by name.
        row.model_as_pinned = check.model.split("/")[-1] in f.model
        cost = fmt_cost(f.cost) + (f" (provider {fmt_cost(f.provider_cost)})" if f.provider_cost is not None else "")
        mark = "ok  " if row.as_expected else "MISS"
        print(f"  {case['id']:<26} {mark} {card['outcome']:<32} {call.elapsed_s:5.2f} s  {cost}")
        if not outcome_ok:
            print(f"      expected: {case['expected']}")
        if want and shows_card and not fact_ok:
            print(f"      expected {want!r} in the fact")
        print(f"      restatement: {card['restatement']}")
        searches = "; ".join(q for q in f.searches if q) or "-"
        print(f"      searches: {len(f.searches)} ({searches})   results: {len(f.results)}   model: {f.model or '?'}"
              + ("" if row.model_as_pinned else "  [NOT the pinned model]"))
        if shows_card:
            row.complete = all(card[k].strip() for k in ("title", "fact", "source_url", "excerpt"))
            print(f"      card: {card['title']} | {card['fact']}")
            print(f"      source: {card['source_title']} <{card['source_url']}>")
            print(f"      excerpt: {card['excerpt'][:300]!r}")
            if card["source_url"]:
                row.in_results = any(same_url(r["url"], card["source_url"]) for r in f.results)
                block = blocklisted(card["source_url"])
                snippet = snippet_match(card, f.results) if check.provider == "perplexity" else "n/a (OpenAI gives no snippets)"
                page, took = page_match(env.client, card)
                slow = f", over the spec's {SPEC_DOWNLOAD_TIMEOUT_S:.0f} s" if took > SPEC_DOWNLOAD_TIMEOUT_S else ""
                # The spec's method: B matches a snippet, A downloads the page.
                if check.provider == "perplexity":
                    row.verified = snippet in ("exact", "normalised")
                else:
                    row.verified = page == "yes" and took <= SPEC_DOWNLOAD_TIMEOUT_S
                row.verified = row.verified and not block
                print(f"      source in search results: {'yes' if row.in_results else 'no'}"
                      f"   blocklisted: {block or 'no'}   cited: {'yes' if f.citations else 'no'}")
                print(f"      excerpt in snippet: {snippet}   excerpt on page: {page} ({took:.1f} s{slow})")
        rows.append(row)
    return rows


def fmt_cost(cost: float | None) -> str:
    return "$?" if cost is None else f"${cost:.5f}"


# --- Main -------------------------------------------------------------------------


class Env:
    def __init__(self, client, recorder, opts):
        self.client, self.recorder, self.opts = client, recorder, opts

    def key(self, check: Check) -> str:
        return os.environ.get(KEY_NAMES[check.provider], "")


def summarise(check: Check, rows: list[Row]) -> str:
    n = len(rows)
    ok = [r for r in rows if r.ok]
    times = [r.elapsed_s for r in ok]
    costs = [r.cost for r in rows if r.cost is not None]
    line = [
        f"| {check.stage} | {check.model} ({check.provider}) | {check.role} ",
        f"| {len(ok)}/{n} ",
        f"| {sum(r.as_expected for r in rows)}/{n} ",
    ]
    if check.kind == "finding":
        cards = [r for r in ok if r.card]
        line.append(
            f"| searched {sum(r.searched for r in ok)}/{len(ok)}, "
            f"pinned model {sum(r.model_as_pinned for r in ok)}/{len(ok)}, "
            f"complete cards {sum(r.complete for r in cards)}/{len(cards)}, "
            f"source in results {sum(r.in_results for r in cards)}/{len(cards)}, "
            f"verified excerpt {sum(r.verified for r in cards)}/{len(cards)} "
        )
    else:
        line.append(f"| probabilities {sum(r.probs for r in ok)}/{len(ok)} ")
    line += [
        f"| {statistics.median(times):.1f} s / {max(times):.1f} s " if times else "| - ",
        f"| {fmt_cost(sum(costs)) if costs else '$?'}",
    ]
    provider_costs = [r.provider_cost for r in rows if r.provider_cost is not None]
    if provider_costs:
        line.append(f" (provider {fmt_cost(sum(provider_costs))})")
    return "".join(line) + " |"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--only", nargs="+", metavar="CHECK", help="run only these checks (see --list)")
    parser.add_argument("--fallbacks", action="store_true", help="also run the fallback checks")
    parser.add_argument("--alt-model", nargs="+", default=[], metavar="MODEL",
                        help="fact-finder B fallbacks to try on Perplexity's Agent API, e.g. xai/grok-4.7")
    parser.add_argument("--cases", nargs="+", metavar="ID", help="run only cases whose id contains one of these")
    parser.add_argument("--pplx-search-type", choices=["web", "fast"], default="web")
    parser.add_argument("--pplx-search-context", choices=["low", "medium", "high"], default="medium")
    parser.add_argument("--pplx-max-steps", type=int, default=2)
    parser.add_argument("--dry-run", action="store_true", help="write the request bodies without calling anyone")
    parser.add_argument("--list", action="store_true", help="list the checks and exit")
    parser.add_argument("--out", type=Path, help="where to write requests and responses (default: out/<time>)")
    opts = parser.parse_args()

    checks = all_checks(opts.alt_model)
    if opts.list:
        for c in checks:
            print(f"{c.name:<28} {c.label}")
        return
    if opts.only:
        unknown = set(opts.only) - {c.name for c in checks}
        if unknown:
            raise SystemExit(f"unknown checks: {', '.join(sorted(unknown))} (see --list)")
        checks = [c for c in checks if c.name in opts.only]
    elif not opts.fallbacks:
        # The --alt-model checks run whenever they are named.
        checks = [c for c in checks if c.role == "provisional" or c.model in opts.alt_model]

    load_secrets()
    config = tomllib.loads((HERE / "cases.toml").read_text())
    place = Place(**config["place"])
    kind_cases = {
        "decision": config["decision"],
        "finding": config["finding"],
        "checking": config["verdict"] + config["same_fact"],
    }
    if opts.cases:
        kind_cases = {k: [c for c in v if any(s in c["id"] for s in opts.cases)] for k, v in kind_cases.items()}

    out_dir = opts.out or HERE / "out" / datetime.now().strftime("%Y-%m-%d-%H%M%S")
    recorder = Recorder(out_dir)
    summary_rows = []
    # HTTP/2: Wikipedia's bot filter answers httpx's HTTP/1.1 requests with 403,
    # which would fail every Wikipedia page download.
    with httpx.Client(http2=True) as client:
        for check in checks:
            cases = kind_cases[check.kind]
            print(f"\n== {check.name}: {check.label}")
            if opts.dry_run:
                dry_run(check, cases, place, opts, out_dir)
                continue
            if not os.environ.get(KEY_NAMES[check.provider]):
                print(f"  skipped: set {KEY_NAMES[check.provider]} in the environment or in a .secrets.* file at the repo root")
                continue
            env = Env(client, recorder, opts)
            runner = run_finding if check.kind == "finding" else run_typed
            rows = runner(check, cases, place, env)
            if rows:
                summary_rows.append(summarise(check, rows))

    if opts.dry_run:
        print(f"\nRequest bodies written to {out_dir}")
        return
    header = (
        "| Stage | Model | Role | Calls OK | As expected | Mechanics | Median / max time | Cost |\n"
        "| --- | --- | --- | --- | --- | --- | --- | --- |"
    )
    table = "\n".join([header, *summary_rows])
    settings = (f"Prompts: {prompt_versions()}.\n"
                f"Perplexity: search_type {opts.pplx_search_type}, search_context_size "
                f"{opts.pplx_search_context}, max_steps {opts.pplx_max_steps}.")
    print(f"\n{table}\n\n{settings}\nRequests and responses: {out_dir}")
    (out_dir / "summary.md").write_text(
        f"# Smoke test {out_dir.name}\n\n{table}\n\n{settings}\n"
    )


def dry_run(check: Check, cases: list[dict], place: Place, opts, out_dir: Path) -> None:
    """Build every request body as a real run would, and write it out."""

    class Capture:
        def __init__(self):
            self.saved = []

        def save(self, check_name, case_id, request, call):
            self.saved.append(case_id)
            path = out_dir / check_name / f"{case_id}.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"request": request}, ensure_ascii=False, indent=2))

    capture = Capture()

    class FakeClient:
        def post(self, url, headers, json, timeout):  # noqa: A002 - httpx's name
            raise httpx.ConnectError("dry run")

    env = Env(FakeClient(), capture, opts)
    runner = run_finding if check.kind == "finding" else run_typed
    with contextlib.redirect_stdout(io.StringIO()):
        runner(check, cases, place, env)
    print(f"  {len(capture.saved)} request bodies")


if __name__ == "__main__":
    main()
