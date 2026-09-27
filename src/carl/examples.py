"""`carl examples`: run the prompts' hand-written example cases against the
configured models, and print each typed answer next to the expected one
(spec section 7, Testing prompts).

The cases are in `prompts/examples/<prompt>.toml`. Run it by hand after a
prompt change, never in CI: it costs money and needs the network, and its
results aren't stored. It needs the stage's key in the environment
(OPENAI_API_KEY for the decision model and fact-finder A, PERPLEXITY_API_KEY
for fact-finder B, OPENROUTER_API_KEY for the fact-checking model). `--case`
runs only the cases whose id starts with it.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import statistics
import tomllib
from collections.abc import Awaitable, Callable, Sequence
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from . import checks, decision, settle
from .checking import SUPPORTED, Judged, band_single
from .config import Config, ConfigError, load_config
from .finding import STAGE_A, STAGE_B, DraftCard, Finding, FindingRequest, key_name, language_name, make_fact_finder
from .location import Locator, Nominatim, Place, date_time
from .models import CallRecord, ModelError, TypedAnswer, http_session, make_typed_model
from .models.questions import TypedPrompt
from .prompts import Prompt, PromptError, load_prompts


def add_parser(sub: argparse._SubParsersAction) -> None:
    examples = sub.add_parser(
        "examples", help="run the prompts' example cases against the configured models (costs money)"
    )
    examples.add_argument(
        "prompt", nargs="?", choices=sorted(RUNNERS), help="the prompt whose cases to run (default: all)"
    )
    examples.add_argument("--config", type=Path, default=Path("config.toml"), help="the config file")
    examples.add_argument("--prompts", type=Path, default=Path("prompts"), help="the prompts folder")
    examples.add_argument("--case", action="append", default=[], metavar="ID",
                          help="run only the cases whose id starts with ID (repeatable)")
    examples.set_defaults(run=run)


def run(args: argparse.Namespace) -> int:
    try:
        config = load_config(args.config)
        prompts = load_prompts(args.prompts)
    except (ConfigError, PromptError) as e:
        print(f"carl examples: {e}", file=sys.stderr)
        return 2
    names = [args.prompt] if args.prompt else sorted(RUNNERS)
    try:
        results = [asyncio.run(RUNNERS[name](config, prompts, args.prompts / "examples" / f"{name}.toml", args.case))
                   for name in names]
    except (OSError, ValueError, KeyError) as e:
        print(f"carl examples: {e}", file=sys.stderr)
        return 2
    return 0 if all(results) else 1


def pick(cases: list[dict[str, Any]], only: Sequence[str]) -> list[dict[str, Any]]:
    """The cases whose id starts with one of `only`; all of them without it."""
    return [case for case in cases if not only or case["id"].startswith(tuple(only))]


async def run_decision(config: Config, prompts: dict[str, Prompt], path: Path, only: Sequence[str] = ()) -> bool:
    """The decision prompt's cases, each through the decision call's own
    fields and outcome rule. True if every one came out as expected."""
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    data["cases"] = pick(data["cases"], only)
    typed = TypedPrompt.load(prompts["decision"])
    stage, s = config.stages.decision, config.decision
    place_and_time = f"{data['place']}. {decision.date_time(data['timezone'])}"
    print(f"decision: prompts/decision.md {typed.version}, {stage.provider} {stage.model}")
    print(f"  place_and_time: {place_and_time}")
    async with http_session() as http:
        model = make_typed_model(stage, config, os.environ, http)

        async def ask(case: dict[str, Any]) -> TypedAnswer | ModelError:
            *before, utterance = case["conversation"]
            earlier = case.get("earlier_candidates", [])
            ids = [c.split(":", 1)[0].strip() for c in earlier]
            question = typed.fill(decision.fields(utterance, before, place_and_time, earlier), ids)
            try:
                return await model.ask(question, stage=decision.STAGE)
            except ModelError as e:
                return e

        answers = await asyncio.gather(*(ask(case) for case in data["cases"]))
    good, cost, estimated = 0, 0.0, False
    for case, answer in zip(data["cases"], answers, strict=True):
        record = answer.record
        cost += record.charged_usd
        estimated |= record.estimated
        took = f"{record.elapsed_s:4.1f} s  ${record.charged_usd:.6f}"
        if isinstance(answer, ModelError):
            print(f"  ERROR {case['id']:<32} {answer.kind}: {record.error_text[:200]}  {took}")
            continue
        got, _ = decision.outcome(answer.answer, answer.probs, s.repeat_threshold, s.candidate_threshold)
        ok = got == case["expected"]
        good += ok
        shown = got if got == answer.answer else f"{got} (chose {answer.answer})"
        expected = "" if ok else f"  expected {case['expected']}"
        print(f"  {'ok   ' if ok else 'MISS '} {case['id']:<32} {shown:<16} p: {probabilities(answer.probs):<24} "
              f"{took}{expected}")
    total = len(data["cases"])
    print(f"{good} of {total} as expected, ${cost:.6f} in all{' (partly estimated)' if estimated else ''}, "
          f"model {answers[0].record.model if answers else '-'}")
    return good == total


def probabilities(probs: dict[str, float] | None) -> str:
    if probs is None:
        return "none given"
    return ", ".join(f"{k} {v:.2f}" for k, v in sorted(probs.items(), key=lambda kv: -kv[1]) if v >= 0.005)


async def run_fact_finding(config: Config, prompts: dict[str, Prompt], path: Path, only: Sequence[str] = ()) -> bool:
    """The fact-finding prompt's cases, each through both fact-finders side
    by side. A fact-finder whose key isn't set is skipped. True if every
    finding came out as expected: the expected outcome, and the expected
    text in the card's fact."""
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    cases = pick(data["cases"], only)
    p = data["place"]
    # What location's methods read of a session. The locator only words the
    # place here: it geocodes nothing.
    table = SimpleNamespace(place=Place(p["neighbourhood"], p["city"], p["region"], p["country"], p["country_code"]),
                            timezone=p["timezone"])
    locator = Locator(config.location, Nominatim())
    place_and_time = locator.place_and_time(table, with_place=True)
    openai_location, perplexity_location = locator.openai_user_location(table), locator.perplexity_user_location(table)
    prompt = prompts["fact-finding"]
    stages = {STAGE_A: config.stages.fact_finder_a, STAGE_B: config.stages.fact_finder_b}
    print(f"fact-finding: prompts/fact-finding.md {prompt.version}")
    for name, stage in stages.items():
        print(f"  {name}: {stage.provider} {stage.model} {stage.params}")
    print(f"  place_and_time: {place_and_time}")
    print(f"  user_location: A {openai_location}, B {perplexity_location}")

    def request(case: dict[str, Any]) -> FindingRequest:
        *before, candidate = case["conversation"]
        return FindingRequest(prompt, case["kind"], candidate, before, place_and_time,
                              language_name(case["card_language"]), openai_location, perplexity_location)

    async with http_session() as http:
        finders = {}
        for name, stage in stages.items():
            if os.environ.get(key_name(stage)):
                finders[name] = make_fact_finder(stage, config, os.environ, http)
            else:
                print(f"  {name}: skipped, {key_name(stage)} isn't set")
        if not finders:
            raise ValueError("no fact-finder has its key set")

        async def find(case: dict[str, Any], name: str) -> Finding | ModelError:
            try:
                return await finders[name].find(request(case), stage=name)
            except ModelError as e:
                return e

        # One case at a time, both fact-finders in parallel, as for a
        # candidate: Perplexity can refuse requests sent all at once (429).
        found: dict[tuple[str, str], Finding | ModelError] = {}
        for case in cases:
            answers = await asyncio.gather(*(find(case, name) for name in finders))
            found |= {(case["id"], name): answer for name, answer in zip(finders, answers, strict=True)}
    good = {name: 0 for name in finders}
    records: dict[str, list[CallRecord]] = {name: [] for name in finders}
    for case in cases:
        print(f"\n{case['id']} ({case['kind']}, {language_name(case['card_language'])}): expected {case['expected']}"
              + (f", {case['expected_in_fact']!r} in the fact" if case.get("expected_in_fact") else ""))
        for name in finders:
            result = found[case["id"], name]
            record = result.record
            records[name].append(record)
            letter = name[-1]
            if isinstance(result, ModelError):
                print(f"  {letter} ERROR {result.kind}: {record.error_text[:300]}  {took(record)}")
                continue
            want = case.get("expected_in_fact", "")
            ok = result.outcome == case["expected"] and (
                result.card is None or want.casefold() in result.card.fact.casefold())
            good[name] += ok
            print(f"  {letter} {'ok  ' if ok else 'MISS'}  {result.outcome:<18} {took(record)}")
            print(f"    restatement: {result.restatement}")
            if result.card is not None:
                card = result.card
                print(f"    card: {card.title} | {card.fact}")
                print(f"    source: {card.source_title} <{card.source_url}>, "
                      f"in the results: {'yes' if result.source_in_results else 'NO'}")
                print(f"    excerpt: {card.excerpt[:300]!r}")
            searches = "; ".join(result.searches) or "-"
            print(f"    {result.search_calls} search(es) charged ({searches}), {len(result.results)} results, "
                  f"{record.input_tokens} tokens in, {record.output_tokens} out, model {result.model}"
                  + ("  [NOT the pinned model]" if result.model_differs else ""))
    print()
    for name in finders:
        rs = records[name]
        times = [r.elapsed_s for r in rs]
        estimated = " (partly estimated)" if any(r.estimated for r in rs) else ""
        provider = [r.provider_cost_usd for r in rs if r.provider_cost_usd is not None]
        own = f", the provider's own ${sum(provider):.5f}" if provider else ""
        print(f"{name}: {good[name]} of {len(cases)} as expected, ${sum(r.charged_usd for r in rs):.5f} in all"
              f"{estimated} (the price table's ${sum(r.cost_usd for r in rs):.5f}{own}), time median "
              f"{statistics.median(times) if times else 0:.1f} s, max {max(times, default=0):.1f} s")
    return all(n == len(cases) for n in good.values())


async def run_fact_checking(config: Config, prompts: dict[str, Prompt], path: Path, only: Sequence[str] = ()) -> bool:
    """The fact-checking prompt's cases: each draft card's verdict, asked with
    the fields a candidate's check gives it, and the band that verdict would
    give a card with a verified excerpt from a source that isn't
    blocklisted. True if every verdict came out as expected."""
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    cases = pick(data["cases"], only)
    typed = TypedPrompt.load(prompts["fact-checking"])
    stage = config.stages.fact_checking
    when = date_time(data["timezone"])
    print(f"fact-checking: prompts/fact-checking.md {typed.version}, {stage.provider} {stage.model}")
    print(f"  date_time: {when}")
    async with http_session() as http:
        model = make_typed_model(stage, config, os.environ, http)

        async def ask(case: dict[str, Any]) -> TypedAnswer | ModelError:
            *before, candidate = case["conversation"]
            card = DraftCard(case["card_title"], case["card_fact"], case["source_url"], case["source_title"],
                             case["excerpt"])
            try:
                return await model.ask(typed.fill(checks.verdict_fields(candidate, before, card, when)),
                                       stage=checks.STAGE)
            except ModelError as e:
                return e

        answers = await asyncio.gather(*(ask(case) for case in cases))
    good, cost, estimated = 0, 0.0, False
    for case, answer in zip(cases, answers, strict=True):
        record = answer.record
        cost += record.charged_usd
        estimated |= record.estimated
        if isinstance(answer, ModelError):
            print(f"  ERROR {case['id']:<20} {answer.kind}: {record.error_text[:200]}  {took(record)}")
            continue
        ok = answer.answer == case["expected"]
        good += ok
        outcome = "claim is wrong" if case["kind"] == "claim" else "question answered"
        p = None if answer.probs is None else answer.probs.get(SUPPORTED, 0.0)
        band = band_single(Judged("B", outcome, True, None, answer.answer, p), config.bands)
        expected = "" if ok else f"  expected {case['expected']}"
        print(f"  {'ok   ' if ok else 'MISS '} {case['id']:<20} {answer.answer:<29} "
              f"p: {probabilities(answer.probs):<56} {band.reason:<23} {took(record)}{expected}")
    print(f"{good} of {len(cases)} as expected, ${cost:.6f} in all{' (partly estimated)' if estimated else ''}, "
          f"model {answers[0].record.model if answers else '-'}")
    return good == len(cases)


async def run_same_fact(config: Config, prompts: dict[str, Prompt], path: Path, only: Sequence[str] = ()) -> bool:
    """The agreement prompt's cases: whether two draft cards state the same
    fact, asked with the fields a candidate's check gives the agreement
    call. True if every answer came out as expected."""
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    cases = pick(data["cases"], only)
    typed = TypedPrompt.load(prompts["same-fact"])
    stage = config.stages.fact_checking
    when = date_time(data["timezone"])
    print(f"same-fact: prompts/same-fact.md {typed.version}, {stage.provider} {stage.model}")
    print(f"  date_time: {when}")
    async with http_session() as http:
        model = make_typed_model(stage, config, os.environ, http)

        async def ask(case: dict[str, Any]) -> TypedAnswer | ModelError:
            fields = checks.agreement_fields(case["candidate"], case["card_1"], case["card_2"], when)
            try:
                return await model.ask(typed.fill(fields), stage=checks.STAGE)
            except ModelError as e:
                return e

        answers = await asyncio.gather(*(ask(case) for case in cases))
    good, cost, estimated = 0, 0.0, False
    for case, answer in zip(cases, answers, strict=True):
        record = answer.record
        cost += record.charged_usd
        estimated |= record.estimated
        if isinstance(answer, ModelError):
            print(f"  ERROR {case['id']:<18} {answer.kind}: {record.error_text[:200]}  {took(record)}")
            continue
        ok = answer.answer == case["expected"]
        good += ok
        expected = "" if ok else f"  expected {case['expected']}"
        print(f"  {'ok   ' if ok else 'MISS '} {case['id']:<18} {answer.answer:<25} "
              f"p: {probabilities(answer.probs):<56} {took(record)}{expected}")
    print(f"{good} of {len(cases)} as expected, ${cost:.6f} in all{' (partly estimated)' if estimated else ''}, "
          f"model {answers[0].record.model if answers else '-'}")
    return good == len(cases)


async def run_settle(config: Config, prompts: dict[str, Prompt], path: Path, only: Sequence[str] = ()) -> bool:
    """The settle prompt's cases, each through the settle call's own fields,
    choices and outcome rule. True if every one came out as expected."""
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    cases = pick(data["cases"], only)
    typed = TypedPrompt.load(prompts["settle"])
    stage = config.stages.decision
    when = date_time(data["timezone"])
    print(f"settle: prompts/settle.md {typed.version}, {stage.provider} {stage.model}")
    print(f"  date_time: {when}")
    async with http_session() as http:
        model = make_typed_model(stage, config, os.environ, http)

        async def ask(case: dict[str, Any]) -> tuple[TypedAnswer | ModelError, list[str]]:
            *before, utterance = case["conversation"]
            live = case["live"]
            lines = [f"{c['id']}: {c['text']}" + (f" [on screen: {c['on_screen']}]" if c.get("on_screen") else "")
                     for c in live]
            shown = [c["id"] for c in live if c.get("on_screen")]
            ids = {settle.SETTLES: [c["id"] for c in live if not c.get("on_screen")], settle.AGREES: shown,
                   settle.DISPUTES: shown}
            question = typed.fill(settle.fields(utterance, before, when, lines), ids)
            try:
                return await model.ask(question, stage=settle.STAGE), list(question.choices)
            except ModelError as e:
                return e, list(question.choices)

        answers = await asyncio.gather(*(ask(case) for case in cases))
    good, cost, estimated = 0, 0.0, False
    for case, (answer, choices) in zip(cases, answers, strict=True):
        record = answer.record
        cost += record.charged_usd
        estimated |= record.estimated
        if isinstance(answer, ModelError):
            print(f"  ERROR {case['id']:<24} {answer.kind}: {record.error_text[:200]}  {took(record)}")
            continue
        got, _ = settle.settle_outcome(answer.answer, answer.probs, choices, config.decision.settle_threshold)
        ok = got == case["expected"]
        good += ok
        shown = got if got == answer.answer else f"{got} (chose {answer.answer})"
        expected = "" if ok else f"  expected {case['expected']}"
        print(f"  {'ok   ' if ok else 'MISS '} {case['id']:<24} {shown:<16} p: {probabilities(answer.probs):<36} "
              f"{took(record)}{expected}")
    print(f"{good} of {len(cases)} as expected, ${cost:.6f} in all{' (partly estimated)' if estimated else ''}, "
          f"model {answers[0][0].record.model if answers else '-'}")
    return good == len(cases)


def took(record: CallRecord) -> str:
    """A call's time and what it counts toward the totals, with Carl's own figure when that differs."""
    cost = f"${record.charged_usd:.5f}"
    if record.provider_cost_usd is not None:
        cost += f" (the price table's ${record.cost_usd:.5f})"
    return f"{record.elapsed_s:4.1f} s  {cost}{' estimated' if record.estimated else ''}"


RUNNERS: dict[str, Callable[[Config, dict[str, Prompt], Path, Sequence[str]], Awaitable[bool]]] = {
    "decision": run_decision,
    "fact-finding": run_fact_finding,
    "fact-checking": run_fact_checking,
    "same-fact": run_same_fact,
    "settle": run_settle,
}
