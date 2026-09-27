"""`carl owner tail`: what the decision model and the candidates' checks did
in a recording session, from its event log, following the log while the
session runs.

    carl owner tail [<id>] [-n N] [-f] [--checks] [--context] [--dev]

By default it shows the decision model's calls. A call is a `model call`
event of stage `decision` or `settle` and its outcome, the `decision` or
`settle` event on the same utterance. Each block shows the utterance the
model was asked about, what Carl made of the answer, the answer's
probabilities, and the call's time, tokens and cost:

    20:57:33  U3 decision → candidate C1
      A1: Me elämme valtamedian taikka valemedian valtakunnassa, …
      claim 0.997 · other 0.003   1.21 s · 571+13 tokens · $0.000064

With `--checks` it shows each candidate's check instead, once it has ended
(its `check` event): the utterance, then for each fact-finder its outcome,
restatement, searches, draft card, source and excerpt, whether the excerpt
was found at the source, and the fact-checking model's verdict; then the
agreement call, the band and the card as sent. Whatever happens to a
candidate after its block (a fact-finder that answered too late, a card
withdrawn) follows as a line of its own.

`--context` adds the prompt's other fields as the model saw them: the
conversation before the utterance, the place and time, and for the decision
model the earlier or live candidates; for checks, also each fact-finder's
search results. Without an id it tails the newest session. Without `-f` it
prints the last N calls or checks and stops; with it, it then polls the
bucket for new log parts (the server writes one about every 10 s) until the
session ends.
"""

from __future__ import annotations

import asyncio
import shutil
import textwrap
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from .owner import HELSINKI, OwnerError, check_id, event_time, fetch, id_time, parse_events
from .storage import Store

POLL_S = 5.0
BATCH = 8  # log parts fetched at a time, reading back from the end: about 80 s, past the 60 s timeout
STAGES = ("decision", "settle")  # a model call's stage, and its outcome event's name

Pair = tuple[dict[str, Any] | None, dict[str, Any] | None]  # (model call, outcome)


class View(Protocol):
    """What `tail` shows: the decision model's calls or the candidates' checks."""

    title: str

    def feed(self, events: list[dict[str, Any]]) -> list[Any]:
        """What these events complete, to show in this order."""

    def unfinished(self) -> list[Any]:
        """What has begun but isn't complete, to show when nothing more will come."""

    def whole(self, item: Any) -> bool:
        """The item was read from its start, not only its end."""

    def render(self, item: Any, *, context: bool, width: int) -> str: ...


class Calls:
    """The decision model's calls: pairs each call with its outcome event,
    which may come in a later log part."""

    title = "The decision model's calls"

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

    @staticmethod
    def whole(pair: Pair) -> bool:
        """Read from its start: its call too, not just its outcome."""
        return pair[0] is not None

    @staticmethod
    def render(pair: Pair, *, context: bool, width: int) -> str:
        return format_call(*pair, context=context, width=width)


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
        lines += textwrap.wrap(line, width, initial_indent=indent, subsequent_indent=indent + hang,
                               break_long_words=False, break_on_hyphens=False) or [indent]
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


# --- The candidates' checks ------------------------------------------------------------

# Events about a candidate that name it as `id`; the rest name it as `candidate`.
BY_ID = ("candidate", "card sent", "card filed", "card withdrawn")
# The decision model's events, which name a candidate for other reasons.
NOT_A_CHECKS = ("decision", "repeat", "settle")
# What can happen to a candidate after its block, shown as a line of its own.
LATE = ("finding", "failure", "check", "card withdrawn")


@dataclass
class Check:
    """One candidate's events, from its `candidate` event on."""

    id: str
    events: list[dict[str, Any]] = field(default_factory=list)
    done: dict[str, Any] | None = None  # its first `check` event: how the check ended

    def first(self, kind: str, **match: Any) -> dict[str, Any] | None:
        return next((e for e in self.events if e.get("event") == kind
                     and all(e.get(k) == v for k, v in match.items())), None)

    def all(self, kind: str, **match: Any) -> list[dict[str, Any]]:
        return [e for e in self.events if e.get("event") == kind and all(e.get(k) == v for k, v in match.items())]


@dataclass(frozen=True)
class Late:
    """An event about a candidate whose block is already shown."""

    id: str
    event: dict[str, Any]


class Checks:
    """The candidates' checks: collects each candidate's events, and hands
    over its check once it has ended."""

    title = "The candidates' checks"

    def __init__(self) -> None:
        self.checks: dict[str, Check] = {}
        self.shown: set[str] = set()
        self.utterances: dict[str, str] = {}  # id → text, for a candidate with no fact-finding call

    def feed(self, events: list[dict[str, Any]]) -> list[Check | Late]:
        """The checks these events end, and what happens to those already shown."""
        out: list[Check | Late] = []
        for e in events:
            kind = e.get("event")
            if kind == "utterance" and isinstance(e.get("id"), str):
                self.utterances[e["id"]] = str(e.get("text", ""))
                continue
            if kind in NOT_A_CHECKS:
                continue
            cid = e.get("id") if kind in BY_ID else e.get("candidate")
            if not isinstance(cid, str):
                continue
            if kind == "model call":
                e = {k: v for k, v in e.items() if k != "response"}  # large, and not shown
            check = self.checks.setdefault(cid, Check(cid))
            check.events.append(e)
            if cid in self.shown:
                if kind in LATE:
                    out.append(Late(cid, e))
            elif kind == "check" and check.done is None:
                check.done = e
                out.append(check)
        return out

    def unfinished(self) -> list[Check | Late]:
        """The candidates still being checked."""
        return [c for c in self.checks.values() if c.done is None and c.id not in self.shown and self.whole(c)]

    @staticmethod
    def whole(item: Check | Late) -> bool:
        """Read from its start: its `candidate` event too."""
        return isinstance(item, Check) and item.first("candidate") is not None

    def render(self, item: Check | Late, *, context: bool, width: int) -> str:
        if isinstance(item, Late):
            return format_late(item)
        self.shown.add(item.id)
        return format_check(item, self.utterances, context=context, width=width)


def cost(calls: list[dict[str, Any]]) -> float:
    total = 0.0
    for call in calls:
        value = call.get("provider_cost_usd")
        value = call.get("cost_usd") if value is None else value
        total += value if isinstance(value, int | float) else 0.0
    return total


def end_text(check: dict[str, Any] | None, shown: str | None = None) -> str:
    """How a check ended, from its `check` event."""
    if check is None:
        return "still being checked"
    state, reason = check.get("state"), check.get("reason")
    if state == "ready":
        return f"shown ({reason})" + (f", {shown}'s card" if shown else "")
    if state == "failed":
        errors = check.get("errors")
        why = check.get("kind") or reason or ", ".join(f"{k} {v}" for k, v in (errors or {}).items()) or "?"
        where = check.get("stage") or "?"
        waiting = check.get("waiting_on")
        return f"failed in {where}: {why}" + (f", waiting on {', '.join(waiting)}" if waiting else "")
    extra = [f"settled by {check['settled_by']}"] if check.get("settled_by") else []
    extra += [f"disputes {check['disputes']}"] if check.get("disputes") else []
    return f"{state} ({', '.join([str(reason), *extra])})"


def excerpt_text(check: Check, finder: str) -> str | None:
    """Whether the draft card's excerpt was found at its source."""
    excerpt = check.first("excerpt", finder=finder)
    blocked = check.first("blocklisted", finder=finder)
    if blocked is not None:
        return f"✗ the source is blocklisted ({blocked.get('suffix')})"
    if excerpt is None:
        return None
    if excerpt.get("method") == "snippet":
        return "✓ found in the search snippets" if excerpt.get("verified") else "✗ not found in the search snippets"
    if excerpt.get("verified"):
        return f"✓ found on the page ({excerpt.get('match')})" if excerpt.get("match") else "✓ found on the page"
    page = check.first("download", finder=finder) or {}
    why = [str(x) for x in (excerpt.get("reason"), page.get("error")) if x]
    return "✗ not found on the page" + (f": {', '.join(why)}" if why else "")


def labelled(label: str, text: str, width: int, indent: str) -> list[str]:
    """`label: text`, wrapped with its continuation lines under the text."""
    return textwrap.wrap(f"{label}: {text}", width, initial_indent=indent,
                         subsequent_indent=indent + " " * (len(label) + 2),
                         break_long_words=False, break_on_hyphens=False) or [indent]


def plural(n: int, noun: str, suffix: str = "s") -> str:
    return f"{n} {noun}{suffix * (n != 1)}"


def format_finder(check: Check, letter: str, findings: dict[str, Any], *, context: bool, width: int) -> list[str]:
    """One fact-finder's part of a check's block."""
    finding = check.first("finding", finder=letter)
    calls = check.all("model call", stage=f"fact-finding {letter}")
    head = f"  {letter}  "
    pad = " " * len(head)

    def first_line(text: str) -> list[str]:
        return textwrap.wrap(text, width, initial_indent=head, subsequent_indent=pad,
                             break_long_words=False, break_on_hyphens=False)

    if finding is None:
        failure = check.first("failure", stage=f"fact-finding {letter}") or {}
        failed = (findings.get("failed") or {}).get(letter) or failure.get("kind")
        if failed:
            text = " ".join(str(failure.get("error_text") or "").split())
            return first_line(f"failed: {failed}" + (f" ({text[:200]})" if text else ""))
        if letter in (findings.get("missed") or []):
            return first_line("missed the wait, and no answer came")
        return first_line("no answer yet")
    done_at, found_at = event_time(check.done), event_time(finding)
    late = done_at is not None and found_at is not None and found_at > done_at
    summary = [str(finding.get("outcome"))]
    if isinstance(after := finding.get("after_s"), int | float):
        summary.append(f"{after} s after the utterance")
    if late:
        summary.append("too late, not used")
    if calls and (numbers := figures(calls[-1] | {"cost_usd": cost(calls), "provider_cost_usd": None})):
        summary.append(numbers)
    results = finding.get("results") or []
    searches = finding.get("search_calls") if isinstance(finding.get("search_calls"), int) else 0
    summary.append(f"{plural(searches, 'search', 'es')}, {plural(len(results), 'result')}")
    lines = first_line(" · ".join(summary))
    body: list[tuple[str, str]] = []
    if finding.get("restatement"):
        body.append(("restated", f"\"{finding['restatement']}\""))
    if queries := finding.get("searches"):
        body.append(("searched", " · ".join(f"\"{q}\"" for q in queries)))
    card = finding.get("card")
    if isinstance(card, dict):
        body.append(("card", f"{card.get('title')}. {card.get('fact')}"))
        body.append(("source", str(card.get("source_url"))))
        body.append(("excerpt", f"\"{card.get('excerpt')}\""))
    if (found := excerpt_text(check, letter)) is not None:
        body.append(("verified", found))
    if (verdict := check.first("verdict", finder=letter)) is not None:
        answer = probabilities(verdict.get("probs")) or verdict.get("answer") or f"failed: {verdict.get('error')}"
        body.append(("verdict", str(answer)))
    elif (skipped := check.first("verdict skipped", finder=letter)) is not None:
        body.append(("verdict", f"skipped ({skipped.get('reason')})"))
    for label, text in body:
        lines += labelled(label, text, width, pad)
    if context and results:
        urls = list(dict.fromkeys(str(r.get("url")) for r in results if isinstance(r, dict)))
        lines.append(f"{pad}results:")
        lines += [f"{pad}  {url}" for url in urls[:10]]
        lines += [f"{pad}  … and {len(urls) - 10} more"] if len(urls) > 10 else []
    return lines


def format_check(check: Check, utterances: dict[str, str] | None = None, *, context: bool = False,
                 width: int = 100) -> str:
    """One candidate's block."""
    candidate = check.first("candidate") or {}
    band = check.first("band") or {}
    everything = [e for e in check.events if e.get("event") == "model call"]
    about = check.done or candidate
    head = [f"{local_time(about)}  {check.id} {candidate.get('kind', '?')} → {end_text(check.done, band.get('shown'))}"]
    if check.done is not None and isinstance(after := check.done.get("after_s"), int | float):
        head.append(f"{after} s")
    if everything:
        head.append(f"${cost(everything):.6f}")
    lines = wrap(" · ".join(head), width, "")
    finding_call = next((e for e in everything if str(e.get("stage", "")).startswith("fact-finding")), None)
    fields = (finding_call or {}).get("fields") or {}
    utterance = candidate.get("utterance")
    if isinstance(fields, dict) and isinstance(fields.get("candidate"), str):
        lines += wrap(fields["candidate"], width, "  ")
    elif utterance in (utterances or {}):
        lines += wrap(f"{utterance}: {(utterances or {})[utterance]}", width, "  ")
    flagged = [f"in {utterance}"] if utterance else []
    if isinstance(p := candidate.get("probability"), int | float):
        flagged.append(f"{candidate.get('kind')} {p:.3f}")
    if language := (candidate.get("card_language") or {}).get("language"):
        flagged.append(f"card language {language}")
    if candidate.get("repeat_of"):
        flagged.append(f"repeat of failed {candidate['repeat_of']}")
    lines += labelled("flagged", " · ".join(flagged), width, "  ")
    findings = check.first("findings") or {}
    letters = {str(e.get("finder")) for e in check.all("finding")}
    letters |= {str(e["stage"]).removeprefix("fact-finding ") for e in everything
                if str(e.get("stage", "")).startswith("fact-finding ")}
    letters |= set(findings.get("used") or []) | set(findings.get("failed") or {}) | set(findings.get("missed") or [])
    for letter in sorted(letters):
        lines += format_finder(check, letter, findings, context=context, width=width)
    if (agreement := check.first("agreement")) is not None:
        answer = probabilities(agreement.get("probs")) or agreement.get("answer") or f"failed: {agreement.get('error')}"
        lines += labelled("agreement", str(answer), width, "  ")
    if (sent := check.first("card sent")) is not None:
        label = " · ".join(str(x) for x in (sent.get("label"), sent.get("tag")) if x)
        filed = check.first("card filed") or {}
        lines += labelled("sent", f"[{label}] {sent.get('title')}. {sent.get('fact')}"
                          + (" (late)" if filed.get("late") else ""), width, "  ")
    if check.done is not None:  # what happened after it ended; a late finding is in its finder's part
        after = check.events[check.events.index(check.done) + 1:]
        for e in after:
            if e.get("event") in LATE and e.get("event") != "finding":
                lines += wrap(f"{local_time(e)}  {late_text(e)}", width, "  ")
    if context and isinstance(fields, dict):
        for name, value in fields.items():
            if name != "candidate":
                lines.append(f"  {name}:")
                lines += wrap(str(value), width, "    ")
    return "\n".join(lines)


def late_text(e: dict[str, Any]) -> str:
    """What happened to a candidate after its check ended."""
    kind = e.get("event")
    if kind == "finding":
        return f"late answer from {e.get('finder')}: {e.get('outcome')}, {e.get('after_s')} s after the utterance"
    if kind == "failure":
        return f"{e.get('stage')} failed: {e.get('kind')}"
    if kind == "card withdrawn":
        return f"card withdrawn ({e.get('reason')})"
    return f"→ {end_text(e)}"


def format_late(late: Late) -> str:
    return f"{local_time(late.event)}  {late.id} {late_text(late.event)}"


async def newest(store: Store) -> str:
    """The id of the newest session with a recording."""
    ids = {k.split("/")[1] for k in await store.list("recordings/") if len(k.split("/")) > 2}
    dated = [(t, i) for i in ids if (t := id_time(i)) is not None]
    if not dated:
        raise OwnerError("there are no recordings")
    return max(dated)[1]


async def read(store: Store, keys: list[str]) -> list[dict[str, Any]]:
    return [e async for part in fetch(store, keys) for e in parse_events(part)]


async def tail(store: Store, session_id: str | None, n: int = 10, *, follow: bool = False, checks: bool = False,
               context: bool = False, poll_s: float = POLL_S, width: int | None = None,
               out: Callable[[str], None] | None = None) -> int:
    """Print the session's last `n` decision-model calls, or with `checks`
    candidates' checks, then with `follow` each new one until the session
    ends or its recording is deleted."""
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
    make: Callable[[], View] = Checks if checks else Calls

    # The last n, reading parts back from the end until they are all found
    # whole. Even for none, one batch: what is under way now began in it.
    events: list[dict[str, Any]] = []
    start = len(keys)
    while True:
        batch = keys[max(0, start - BATCH):start]
        start -= len(batch)
        events = await read(store, batch) + events
        view = make()
        items = view.feed(events)
        if not n or start <= 0 or sum(map(view.whole, items)) >= n:
            break
    ended = any(e.get("event") == "session end" for e in events)

    started = id_time(session_id)
    when = started.astimezone(HELSINKI).strftime("%Y-%m-%d %H:%M") if started else "?"
    state = "ended" if ended else "following; Ctrl-C stops" if follow else "no end event yet"
    show(f"Session {session_id}, started {when} Helsinki time ({state}). {view.title}:")
    shown = [item for item in items if view.whole(item)][-n:] if n else []
    if not follow or ended:
        shown += view.unfinished()
    for item in shown:
        show("")
        show(view.render(item, context=context, width=width))
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
        items = view.feed(events)
        if any(e.get("event") == "session end" for e in events):
            items += view.unfinished()
        for item in items:
            show("")
            show(view.render(item, context=context, width=width))
        if any(e.get("event") == "session end" for e in events):
            show("\nThe session has ended.")
            return 0
