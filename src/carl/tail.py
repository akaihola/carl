"""`carl owner tail`: the decision model's calls in a recording session's
event log, one block per call, following the log while the session runs.

    carl owner tail [<id>] [-n N] [-f] [--context] [--dev]

A call is a `model call` event of stage `decision` or `settle` and its
outcome, the `decision` or `settle` event on the same utterance. Each block
shows the utterance the model was asked about, what Carl made of the
answer, the answer's probabilities, and the call's time, tokens and cost:

    20:57:33  U3 decision → candidate C1
      A1: Me elämme valtamedian taikka valemedian valtakunnassa, …
      claim 0.997 · other 0.003   1.21 s · 571+13 tokens · $0.000064

`--context` adds the prompt's other fields as the model saw them: the
conversation before the utterance, the place and time, and the earlier or
live candidates. Without an id it tails the newest session. Without `-f` it
prints the last N calls and stops; with it, it then polls the bucket for new
log parts (the server writes one about every 10 s) until the session ends.
"""

from __future__ import annotations

import asyncio
import shutil
import textwrap
from collections.abc import Callable
from typing import Any

from .owner import HELSINKI, OwnerError, check_id, event_time, fetch, id_time, parse_events
from .storage import Store

POLL_S = 5.0
BATCH = 8  # log parts fetched at a time, reading back from the end
STAGES = ("decision", "settle")  # a model call's stage, and its outcome event's name

Pair = tuple[dict[str, Any] | None, dict[str, Any] | None]  # (model call, outcome)


class Calls:
    """Pairs each decision-model call with its outcome event, which may come
    in a later log part."""

    def __init__(self) -> None:
        self.waiting: dict[tuple[str, Any], dict[str, Any]] = {}  # (stage, utterance) → model call

    def feed(self, events: list[dict[str, Any]]) -> list[Pair]:
        """The calls these events complete, in the order they were decided.
        An outcome whose call came before the events read has None for it."""
        done: list[Pair] = []
        for e in events:
            kind = e.get("event")
            if kind == "model call" and e.get("stage") in STAGES:
                self.waiting[(e["stage"], e.get("utterance"))] = e
            elif kind in STAGES:
                done.append((self.waiting.pop((kind, e.get("utterance")), None), e))
        return done

    def unfinished(self) -> list[Pair]:
        """The calls whose outcome isn't in the log yet."""
        pairs: list[Pair] = [(call, None) for call in self.waiting.values()]
        self.waiting.clear()
        return pairs


def outcome_text(stage: str, outcome: dict[str, Any] | None) -> str:
    """What Carl made of the answer."""
    if outcome is None:
        return "…"
    what, candidate = outcome.get("outcome"), outcome.get("candidate")
    if what in ("dropped", "failed"):
        return f"{what}: {outcome.get('error')}"
    if stage == "decision" and what == "candidate":
        return f"candidate {candidate}"
    if what == "repeat":
        return f"repeat of {candidate or 'an earlier candidate'}"
    if what == "repeat of failed":
        return f"candidate {candidate}, checking failed {outcome.get('repeat_of')} anew"
    if stage == "settle" and what != "none" and outcome.get("applied") is False:
        return f"{what} (not applied)"
    return str(what)


def probabilities(probs: Any) -> str:
    if not isinstance(probs, dict) or not probs:
        return ""
    ranked = sorted(probs.items(), key=lambda kv: -(kv[1] if isinstance(kv[1], int | float) else 0))
    return " · ".join(f"{k} {v:.3f}" if isinstance(v, int | float) else f"{k} {v}" for k, v in ranked)


def figures(call: dict[str, Any]) -> str:
    """The call's time, tokens and cost; its HTTP status and error on failure."""
    parts = []
    if isinstance(elapsed := call.get("elapsed_s"), int | float):
        parts.append(f"{elapsed:.2f} s")
    tokens_in, tokens_out = call.get("input_tokens"), call.get("output_tokens")
    if tokens_in is not None or tokens_out is not None:
        estimated = "~" if call.get("estimated") else ""
        parts.append(f"{estimated}{tokens_in or 0}+{tokens_out or 0} tokens")
    cost = call.get("provider_cost_usd")
    cost = call.get("cost_usd") if cost is None else cost
    if isinstance(cost, int | float):
        parts.append(f"${cost:.6f}")
    if call.get("error"):
        status = call.get("status")
        text = " ".join(str(call.get("error_text") or call.get("error_code") or "").split())
        parts.append(" ".join(p for p in (f"HTTP {status}" if status else "", text[:200]) if p))
    return " · ".join(parts)


def local_time(event: dict[str, Any] | None) -> str:
    t = event_time(event)
    return t.astimezone(HELSINKI).strftime("%H:%M:%S") if t else "--:--:--"


def wrap(text: str, width: int, indent: str) -> list[str]:
    """Each line of `text` wrapped, continuation lines indented past a
    leading speaker label (`A1: `)."""
    lines = []
    for line in text.splitlines() or [""]:
        label, sep, _ = line.partition(": ")
        hang = " " * (len(label) + 2) if sep and len(label) <= 4 else ""
        lines += textwrap.wrap(line, width, initial_indent=indent, subsequent_indent=indent + hang) or [indent]
    return lines


def format_call(call: dict[str, Any] | None, outcome: dict[str, Any] | None, *, context: bool = False,
                width: int = 100) -> str:
    """One call's block."""
    about = outcome or call or {}
    stage = (call or {}).get("stage") or (outcome or {}).get("event") or "?"
    lines = [f"{local_time(about)}  {about.get('utterance', '?')} {stage} → {outcome_text(stage, outcome)}"]
    fields = (call or {}).get("fields") or {}
    if isinstance(fields, dict) and isinstance(fields.get("utterance"), str):
        lines += wrap(fields["utterance"], width, "  ")
    elif call is None:
        lines.append("  (its call is in an earlier log part)")
    numbers = "   ".join(p for p in (probabilities((outcome or {}).get("probs")), figures(call or {})) if p)
    if numbers:
        lines += wrap(numbers, width, "  ")
    if context and isinstance(fields, dict):
        for name, value in fields.items():
            if name != "utterance":
                lines.append(f"  {name}:")
                lines += wrap(str(value), width, "    ")
    return "\n".join(lines)


async def newest(store: Store) -> str:
    """The id of the newest session with a recording."""
    ids = {k.split("/")[1] for k in await store.list("recordings/") if len(k.split("/")) > 2}
    dated = [(t, i) for i in ids if (t := id_time(i)) is not None]
    if not dated:
        raise OwnerError("there are no recordings")
    return max(dated)[1]


async def read(store: Store, keys: list[str]) -> list[dict[str, Any]]:
    return [e async for part in fetch(store, keys) for e in parse_events(part)]


async def tail(store: Store, session_id: str | None, n: int = 10, *, follow: bool = False, context: bool = False,
               poll_s: float = POLL_S, width: int | None = None, out: Callable[[str], None] | None = None) -> int:
    """Print the session's last `n` decision-model calls, then with `follow`
    each new one until the session ends or its recording is deleted."""
    def show(text: str) -> None:
        if out is None:
            print(text, flush=True)
        else:
            out(text)

    session_id = check_id(session_id) if session_id else await newest(store)
    width = width or max(40, shutil.get_terminal_size((100, 24)).columns)
    prefix = f"recordings/{session_id}/events/"
    keys = await store.list(prefix)
    if not keys:
        raise OwnerError(f"session {session_id} has no event log: its recording was stopped and deleted, "
                         "has expired, or never was")

    # The last n calls, reading parts back from the end until they are all found.
    events: list[dict[str, Any]] = []
    start = len(keys)
    while True:
        batch = keys[max(0, start - BATCH):start] if n else keys[-1:]
        start -= len(batch)
        events = await read(store, batch) + events
        calls = Calls()
        pairs = calls.feed(events)
        if not n or start <= 0 or sum(call is not None for call, _ in pairs) >= n:
            break
    ended = any(e.get("event") == "session end" for e in events)

    started = id_time(session_id)
    when = started.astimezone(HELSINKI).strftime("%Y-%m-%d %H:%M") if started else "?"
    state = "ended" if ended else "following; Ctrl-C stops" if follow else "no end event yet"
    show(f"Session {session_id}, started {when} Helsinki time ({state}). The decision model's calls:")
    shown = pairs[-n:] if n else []
    if not follow or ended:
        shown += calls.unfinished()
    for call, outcome in shown:
        show("")
        show(format_call(call, outcome, context=context, width=width))
    if n and not shown:
        show("(none yet)")
    if not follow:
        return 0
    if ended:
        show("\nThe session has ended.")
        return 0

    last = keys[-1]
    while True:
        await asyncio.sleep(poll_s)
        keys = await store.list(prefix)
        if not keys:
            show("\nThe recording was stopped and deleted.")
            return 0
        new = [k for k in keys if k > last]
        if not new:
            continue
        last = new[-1]
        events = await read(store, new)
        for call, outcome in calls.feed(events):
            show("")
            show(format_call(call, outcome, context=context, width=width))
        if any(e.get("event") == "session end" for e in events):
            for call, outcome in calls.unfinished():
                show("")
                show(format_call(call, outcome, context=context, width=width))
            show("\nThe session has ended.")
            return 0
