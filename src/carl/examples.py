"""`carl examples`: run the prompts' hand-written example cases against the
configured models, and print each typed answer next to the expected one
(spec section 7, Testing prompts).

The cases are in `prompts/examples/<prompt>.toml`. Run it by hand after a
prompt change, never in CI: it costs money and needs the network, and its
results aren't stored. It needs the stage's key in the environment
(OPENAI_API_KEY for the decision model).
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import tomllib
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from . import decision
from .config import Config, ConfigError, load_config
from .models import ModelError, TypedAnswer, http_session, make_typed_model
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
        results = [asyncio.run(RUNNERS[name](config, prompts, args.prompts / "examples" / f"{name}.toml"))
                   for name in names]
    except (OSError, ValueError, KeyError) as e:
        print(f"carl examples: {e}", file=sys.stderr)
        return 2
    return 0 if all(results) else 1


async def run_decision(config: Config, prompts: dict[str, Prompt], path: Path) -> bool:
    """The decision prompt's cases, each through the decision call's own
    fields and outcome rule. True if every one came out as expected."""
    data = tomllib.loads(path.read_text(encoding="utf-8"))
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


RUNNERS: dict[str, Callable[[Config, dict[str, Prompt], Path], Awaitable[bool]]] = {"decision": run_decision}
