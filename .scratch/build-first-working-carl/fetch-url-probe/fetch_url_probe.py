"""Can Perplexity's `fetch_url` stand in for Carl's own source-page download?

Fact-finder A's excerpt is verified by downloading its source page on the
server (`carl.checking.page_match`). A browser can't do that for most sites,
so this probe measures the alternative: one call to Perplexity's Agent API
with only the `fetch_url` tool, whose `fetch_url_results` item carries the
page text as Perplexity's fetcher extracted it, not as the model wrote it.

For each source URL it does both, one after the other:

1. **Carl's download**: `page_match` with the card's excerpt and the
   config's timeout, exactly as the pipeline runs it; then the page's text
   again without the timeout, for the depth probes.
2. **fetch_url**: one streamed Agent API call (`--model`, reasoning `none`,
   one step), timed to the `fetch_url_results` event (all Carl would wait
   for) and to the end of the response. Perplexity's own cost is kept.

and checks:

- whether the card's excerpt is found in each text (`find_excerpt`), and in
  the fetched text with its Markdown markup stripped;
- **depth probes**: a dozen words from a line of Carl's page text at 5 %,
  25 %, 50 %, 75 % and 95 % of its length, looked for in the fetched text.
  A probe found at 95 % means the fetched text reaches the end of the page;
  misses only at the deep end mean it was cut short.

The URLs are the sources fact-finder A cites for the fact-finding example
cases (`prompts/examples/fact-finding.toml`), plus the pages in
`pages.toml`, which have no card excerpt. Run it from the repo root:

    uv run .scratch/build-first-working-carl/fetch-url-probe/fetch_url_probe.py

It needs OPENAI_API_KEY (fact-finder A; `--no-finder` skips it) and
PERPLEXITY_API_KEY. The fetch calls cost about $0.0012 each, and fact-finder
A's calls come on top. It writes every result, both texts of each page and a
summary to `out/<time>/`. See README.md.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import statistics
import sys
import time
import tomllib
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import aiohttp
import httpx

from carl.checking import download_client, find_excerpt, normalize, page_match, page_text
from carl.config import load_config
from carl.finding import STAGE_A, FindingRequest, language_name, make_fact_finder
from carl.location import Locator, Nominatim, Place
from carl.models import ModelError, http_session
from carl.prompts import load_prompts

HERE = Path(__file__).resolve().parent
AGENT_URL = "https://api.perplexity.ai/v1/agent"
FETCH_MODEL = "openai/gpt-6-luna"
INSTRUCTIONS = "Call fetch_url on the URL you are given, then reply with the single word OK."
FETCH_TIMEOUT_S = 30
TEXT_TIMEOUT_S = 15
DEPTHS = (0.05, 0.25, 0.5, 0.75, 0.95)
PROBE_WORDS = 12
# Perplexity can refuse requests that come close together (429).
RETRIES, RETRY_WAIT_S = 2, 5.0
FAILED = re.compile(r"^\s*\[fetch_url:|no_result_returned")
# In a failure marker: "… crawler error bad_robots_code: …".
CRAWLER_ERROR = re.compile(r"crawler error (\w+)")


def reason(fetched: Fetched) -> str:
    """The status, with the crawler's error code when the marker gives one."""
    code = CRAWLER_ERROR.search(fetched.marker)
    return f"{fetched.status} ({code.group(1)})" if fetched.status == "failed" and code else fetched.status


@dataclass
class Source:
    url: str
    excerpt: str = ""  # the card's excerpt; none for pages.toml
    origin: str = ""  # the case id, or the page's note


@dataclass
class Fetched:
    """One fetch_url call. `status` is `ok`, `failed` (Perplexity's failure
    marker, kept in `marker`), `no-content` (no text and no marker),
    `not-called` (no fetch_url_results), `http <code>` or `error`."""

    status: str
    text: str = ""
    title: str = ""
    marker: str = ""
    results_s: float | None = None  # to the fetch_url_results event
    total_s: float = 0.0
    cost_usd: float | None = None
    input_tokens: int | None = None
    model: str = ""
    retries: int = 0
    error: str = ""


@dataclass
class Row:
    source: Source
    carl: dict[str, Any]  # PageMatch.event(), or {} without an excerpt
    carl_text_status: str
    carl_chars: int
    fetched: Fetched
    fetch_chars: int
    excerpt_in_fetch: str | None = None
    excerpt_in_fetch_stripped: str | None = None
    probes: list[dict[str, Any]] = field(default_factory=list)


# --- Fact-finder A's cards ---------------------------------------------------------------------------


async def cards_from_a(runs: int, only: list[str]) -> list[Source]:
    """Fact-finder A's draft cards for the fact-finding example cases: one Source per card."""
    config = load_config(Path("config.toml"))
    prompt = load_prompts(Path("prompts"))["fact-finding"]
    data = tomllib.loads(Path("prompts/examples/fact-finding.toml").read_text(encoding="utf-8"))
    cases = [c for c in data["cases"] if not only or c["id"].startswith(tuple(only))]
    p = data["place"]
    table = SimpleNamespace(place=Place(p["neighbourhood"], p["city"], p["region"], p["country"], p["country_code"]),
                            timezone=p["timezone"])
    locator = Locator(config.location, Nominatim())
    place_and_time = locator.place_and_time(table, with_place=True)
    sources: list[Source] = []
    async with http_session() as http:
        finder = make_fact_finder(config.stages.fact_finder_a, config, os.environ, http)
        for run in range(runs):
            for case in cases:
                *before, candidate = case["conversation"]
                request = FindingRequest(prompt, case["kind"], candidate, before, place_and_time,
                                         language_name(case["card_language"]),
                                         locator.openai_user_location(table), locator.perplexity_user_location(table))
                try:
                    finding = await finder.find(request, stage=STAGE_A)
                except ModelError as e:
                    print(f"  A {case['id']}: {e.kind} {e.record.error_text[:200]}")
                    continue
                card = finding.card
                print(f"  A {case['id']} (run {run + 1}): {finding.outcome}"
                      + (f" <{card.source_url}>" if card else ""))
                if card is not None:
                    sources.append(Source(card.source_url, card.excerpt, case["id"]))
    return sources


# --- Carl's download ---------------------------------------------------------------------------------


async def carl_text(url: str, client: httpx.AsyncClient) -> tuple[str, str]:
    """The page's visible text, as `page_match` would search it, without its
    timeout or size cap: (status, text)."""
    try:
        response = await client.get(url.strip(), timeout=TEXT_TIMEOUT_S)
    except Exception as e:  # noqa: BLE001 - any failure is a result here
        return f"error {type(e).__name__}", ""
    media_type = response.headers.get("content-type", "").split(";")[0].strip().lower()
    if not response.is_success:
        return f"http {response.status_code}", ""
    if media_type == "text/plain":
        return "ok", response.text
    if media_type not in ("text/html", "application/xhtml+xml"):
        return f"not-html {media_type}", ""
    return "ok", page_text(response.text)


# --- fetch_url ---------------------------------------------------------------------------------------


async def fetch_url(url: str, http: aiohttp.ClientSession, key: str, model: str) -> Fetched:
    """One streamed Agent API call with only `fetch_url`, retried on 429."""
    body = {
        "model": model, "store": False, "stream": True, "max_steps": 1, "max_output_tokens": 50,
        "reasoning": {"effort": "none"}, "tools": [{"type": "fetch_url", "max_urls": 1}],
        "instructions": INSTRUCTIONS, "input": url,
    }
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    for attempt in range(RETRIES + 1):
        start = time.perf_counter()
        got = Fetched("not-called", retries=attempt)
        try:
            async with asyncio.timeout(FETCH_TIMEOUT_S), http.post(AGENT_URL, json=body, headers=headers) as resp:
                if resp.status != 200:
                    got.status, got.error = f"http {resp.status}", (await resp.text())[:300]
                else:
                    # Not `async for line in resp.content`: a long page comes
                    # as one `data:` line, longer than aiohttp's line limit.
                    buffer = b""
                    async for chunk in resp.content.iter_any():
                        *lines, buffer = (buffer + chunk).split(b"\n")
                        for line in lines:
                            if line.startswith(b"data:") and line[5:].strip().startswith(b"{"):
                                read_event(json.loads(line[5:]), got, time.perf_counter() - start)
        except TimeoutError:
            got.status, got.error = "error", f"timeout after {FETCH_TIMEOUT_S} s"
        except (aiohttp.ClientError, json.JSONDecodeError) as e:
            got.status, got.error = "error", f"{type(e).__name__}: {e}"
        got.total_s = time.perf_counter() - start
        if got.status != "http 429" or attempt == RETRIES:
            return got
        await asyncio.sleep(RETRY_WAIT_S)
    raise AssertionError("unreachable")


def read_event(event: dict[str, Any], got: Fetched, at_s: float) -> None:
    kind = event.get("type")
    if kind == "response.reasoning.fetch_url_results" and got.results_s is None:
        got.results_s = at_s
        # On 2026-09-28 bfi.org.uk came back as `contents: null` ("Fetched
        # content from 0 URLs"), with no failure marker.
        contents = event.get("contents") or [{}]
        text = str(contents[0].get("snippet") or "")
        got.title = str(contents[0].get("title") or "")
        if FAILED.search(text[:500]):
            got.status, got.marker = "failed", text[:300]
        elif not text.strip():
            got.status, got.marker = "no-content", str(event.get("thought") or "")
        else:
            got.status, got.text = "ok", text
    elif kind in ("response.completed", "response.failed", "response.incomplete"):
        response = event.get("response") or {}
        got.model = str(response.get("model") or "")
        usage = response.get("usage") or {}
        cost = (usage.get("cost") or {}).get("total_cost")
        got.cost_usd = float(cost) if isinstance(cost, int | float) else None
        got.input_tokens = usage.get("input_tokens")
        if kind != "response.completed" and got.status == "not-called":
            got.status, got.error = "error", json.dumps(response.get("error"))[:300]


# --- Matching ----------------------------------------------------------------------------------------

_LINK = re.compile(r"!?\[([^\]]*)\]\([^)]*\)")
# Line marks first (headings, numbered and bulleted list items, quotes), then
# emphasis and code marks: every `*` and backquote, and `_` except inside a
# word (snake_case).
_LINE_MARKS = re.compile(r"^\s*(#+|\d+\.|[-*+]|>)\s", re.M)
_INLINE_MARKS = re.compile(r"[*`]|(?<!\w)_+|_+(?!\w)")


def strip_markdown(text: str) -> str:
    """The text with Markdown links, images, emphasis, code marks, heading and list marks taken out."""
    return _INLINE_MARKS.sub("", _LINE_MARKS.sub("", _LINK.sub(r"\1", text)))


def depth_probes(text: str) -> list[tuple[float, str]]:
    """Up to one probe per depth: the first PROBE_WORDS words of the first
    line of prose (8 words or more) starting at or after that depth, or the
    last such line before it."""
    lines, offset = [], 0
    for line in text.split("\n"):
        words = normalize(line).split()
        if len(words) >= 8 and "|" not in line:
            lines.append((offset, " ".join(words[:PROBE_WORDS])))
        offset += len(line) + 1
    probes: list[tuple[float, str]] = []
    for depth in DEPTHS:
        at = depth * offset
        after = [probe for start, probe in lines if start >= at]
        before = [probe for start, probe in lines if start < at]
        probe = after[0] if after else before[-1] if before else ""
        if probe and all(probe != p for _, p in probes):
            probes.append((depth, probe))
    return probes


# --- The run -----------------------------------------------------------------------------------------


async def probe(sources: list[Source], model: str, out: Path) -> list[Row]:
    config = load_config(Path("config.toml"))
    timeout_s = config.candidates.source_download_timeout_s
    key = os.environ["PERPLEXITY_API_KEY"]
    rows: list[Row] = []
    (out / "pages").mkdir(parents=True, exist_ok=True)
    async with download_client() as client, http_session() as http:
        for n, source in enumerate(sources, 1):
            carl = (await page_match(source.excerpt, source.url, timeout_s, client=client)).event() \
                if source.excerpt else {}
            text_status, text = await carl_text(source.url, client)
            fetched = await fetch_url(source.url, http, key, model)
            row = Row(source, carl, text_status, len(text), fetched, len(fetched.text))
            if source.excerpt and fetched.text:
                row.excerpt_in_fetch = find_excerpt(source.excerpt, fetched.text)
                row.excerpt_in_fetch_stripped = find_excerpt(source.excerpt, strip_markdown(fetched.text))
            if text and fetched.text:
                stripped = strip_markdown(fetched.text)
                row.probes = [{"depth": d, "probe": p, "found": find_excerpt(p, fetched.text),
                               "found_stripped": find_excerpt(p, stripped)} for d, p in depth_probes(text)]
            (out / "pages" / f"{n:02}-carl.txt").write_text(text, encoding="utf-8")
            (out / "pages" / f"{n:02}-fetch.txt").write_text(fetched.text or fetched.marker, encoding="utf-8")
            rows.append(row)
            print(line_for(n, row))
    return rows


def line_for(n: int, row: Row) -> str:
    f, c = row.fetched, row.carl
    carl = "-" if not c else ("verified" if c["verified"] else c["reason"]) + f" {c['elapsed_s']:.1f}s"
    fetch = reason(f) + (f" {f.results_s:.1f}/{f.total_s:.1f}s" if f.results_s else f" {f.total_s:.1f}s")
    excerpt = "" if not row.source.excerpt else \
        f" excerpt {row.excerpt_in_fetch or row.excerpt_in_fetch_stripped and 'stripped' or 'MISSING'}"
    depths = " ".join(f"{p['depth']:.2f}{'+' if p['found'] or p['found_stripped'] else '-'}" for p in row.probes)
    return (f"{n:2} {row.source.url[:70]:<70} carl {carl:<18} text {row.carl_text_status} {row.carl_chars:>7}"
            f" | fetch {fetch:<20} {row.fetch_chars:>7}{excerpt} {depths}")


def pct(values: list[float], q: float) -> float:
    values = sorted(values)
    return values[min(len(values) - 1, round(q * (len(values) - 1)))]


def timing(values: list[float]) -> str:
    if not values:
        return "-"
    return f"median {statistics.median(values):.1f} s, p90 {pct(values, 0.9):.1f} s, max {max(values):.1f} s"


def summary(rows: list[Row], model: str) -> str:
    cards = [r for r in rows if r.source.excerpt]
    ok = [r for r in rows if r.fetched.status == "ok"]
    probes = [p for r in rows for p in r.probes]
    costs = [r.fetched.cost_usd for r in rows if r.fetched.cost_usd is not None]
    lines = [
        f"# fetch_url probe, {datetime.now(UTC):%Y-%m-%d %H:%M} UTC",
        "",
        f"{len(rows)} URLs ({len(cards)} fact-finder A cards), fetch_url through `{model}`.",
        "",
        "## Did each get the page?",
        "",
        f"- Carl's text download: {sum(r.carl_text_status == 'ok' for r in rows)} of {len(rows)}.",
        f"- fetch_url: {len(ok)} of {len(rows)} "
        f"({', '.join(f'{s} {n}' for s, n in count(reason(r.fetched) for r in rows).items())}).",
        f"- Only Carl: {sum(r.carl_text_status == 'ok' and r.fetched.status != 'ok' for r in rows)}; "
        f"only fetch_url: {sum(r.carl_text_status != 'ok' and r.fetched.status == 'ok' for r in rows)}.",
        "",
        "## Card excerpts",
        "",
        f"- Verified by Carl's `page_match`: {sum(bool(r.carl.get('verified')) for r in cards)} of {len(cards)} "
        f"({', '.join(f'{s} {n}' for s, n in count(r.carl.get('reason') or 'verified' for r in cards).items())}).",
        f"- Found in fetch_url's text: {sum(bool(r.excerpt_in_fetch) for r in cards)} of {len(cards)}; "
        f"with Markdown stripped: {sum(bool(r.excerpt_in_fetch_stripped) for r in cards)}.",
        f"- Verified by Carl but missing from fetch_url: "
        f"{sum(bool(r.carl.get('verified')) and not r.excerpt_in_fetch_stripped for r in cards)}; "
        f"found by fetch_url but not by Carl: "
        f"{sum(not r.carl.get('verified') and bool(r.excerpt_in_fetch_stripped) for r in cards)}.",
        "",
        "## How far fetch_url's text reaches (depth probes, both texts in hand)",
        "",
        "| Depth | Probes | Found | Found with Markdown stripped |",
        "| --- | --- | --- | --- |",
    ]
    for depth in DEPTHS:
        at = [p for p in probes if p["depth"] == depth]
        lines.append(f"| {depth:.0%} | {len(at)} | {sum(bool(p['found']) for p in at)} "
                     f"| {sum(bool(p['found_stripped']) for p in at)} |")
    missed = [(n, p) for n, r in enumerate(rows, 1) for p in r.probes if not (p["found"] or p["found_stripped"])]
    lines += ["", "Missed probes, to tell a cut-off page from menus and footers left out on purpose:", ""]
    lines += [f"- #{n} at {p['depth']:.0%}: {p['probe']!r}" for n, p in missed] or ["- none"]
    both = [r for r in rows if r.carl_chars and r.fetch_chars]
    ratios = [r.fetch_chars / r.carl_chars for r in both]
    lines += [
        "",
        f"fetch_url's text length over Carl's: {timing_plain(ratios)}; longest fetched text "
        f"{max((r.fetch_chars for r in rows), default=0):,} characters.",
        "",
        "## Time and cost",
        "",
        f"- Carl's `page_match` (card excerpts): {timing([r.carl['elapsed_s'] for r in cards if r.carl])}.",
        f"- fetch_url to its `fetch_url_results` event: {timing([r.fetched.results_s for r in ok])}.",
        f"- fetch_url to the end of the response: {timing([r.fetched.total_s for r in ok])}.",
        f"- Cost, Perplexity's figure: ${sum(costs):.4f} for {len(costs)} calls"
        + (f", median ${statistics.median(costs):.4f}, max ${max(costs):.4f}." if costs else "."),
        f"- Retries after a 429: {sum(r.fetched.retries for r in rows)}.",
        "",
        "## Each URL",
        "",
        "| # | URL | From | Carl | fetch_url | Excerpt in fetch | Depths found |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for n, r in enumerate(rows, 1):
        carl = "-" if not r.carl else (r.carl.get("match") or r.carl.get("reason")) + f", {r.carl['elapsed_s']:.1f} s"
        fetch = reason(r.fetched) + (f", {r.fetched.results_s:.1f} s" if r.fetched.results_s else "")
        excerpt = "-" if not r.source.excerpt else (
            r.excerpt_in_fetch or (r.excerpt_in_fetch_stripped and f"{r.excerpt_in_fetch_stripped} (stripped)")
            or "no")
        depths = " ".join(f"{p['depth']:.0%}" for p in r.probes if p["found"] or p["found_stripped"]) or "-"
        lines.append(f"| {n} | {r.source.url} | {r.source.origin} | {carl}; text {r.carl_text_status}, "
                     f"{r.carl_chars:,} ch | {fetch}, {r.fetch_chars:,} ch | {excerpt} | {depths} |")
    return "\n".join(lines) + "\n"


def timing_plain(values: list[float]) -> str:
    if not values:
        return "-"
    return f"median {statistics.median(values):.2f}, min {min(values):.2f}, max {max(values):.2f}"


def count(items: Any) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        counts[item] = counts.get(item, 0) + 1
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--runs", type=int, default=1, help="times to run fact-finder A over the cases")
    parser.add_argument("--case", action="append", default=[], metavar="ID", help="only cases whose id starts so")
    parser.add_argument("--no-finder", action="store_true", help="skip fact-finder A: pages.toml and --url only")
    parser.add_argument("--no-pages", action="store_true", help="leave out pages.toml")
    parser.add_argument("--url", action="append", default=[], help="another page to probe (repeatable)")
    parser.add_argument("--model", default=FETCH_MODEL, help="the Agent API model that calls fetch_url")
    args = parser.parse_args()
    for name in ["PERPLEXITY_API_KEY"] + ([] if args.no_finder else ["OPENAI_API_KEY"]):
        if not os.environ.get(name):
            print(f"{name} isn't set", file=sys.stderr)
            return 2
    sources: list[Source] = []
    if not args.no_finder:
        print("Fact-finder A on the fact-finding example cases:")
        sources += asyncio.run(cards_from_a(args.runs, args.case))
    if not args.no_pages:
        pages = tomllib.loads((HERE / "pages.toml").read_text(encoding="utf-8"))["pages"]
        sources += [Source(p["url"], "", p.get("note", "")) for p in pages]
    sources += [Source(url, "", "--url") for url in args.url]
    out = HERE / "out" / datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    print(f"\n{len(sources)} URLs; carl = page_match with the card's excerpt; fetch = status, "
          f"s to fetch_url_results / to the end; depths: + found in fetch_url's text")
    rows = asyncio.run(probe(sources, args.model, out))
    with (out / "results.jsonl").open("w", encoding="utf-8") as f:
        for row in rows:
            record = asdict(row)
            record["fetched"].pop("text")
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    text = summary(rows, args.model)
    (out / "summary.md").write_text(text, encoding="utf-8")
    print("\n" + text + f"\nWritten to {out.relative_to(Path.cwd()) if out.is_relative_to(Path.cwd()) else out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
