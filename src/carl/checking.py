"""Checking draft cards (spec sections 6 and 7): matching an excerpt against
its source, the blocklist, the bands with their reason codes, and the words
Carl adds to a card in the card language.

Everything here is pure logic except `page_match`, which downloads
fact-finder A's source page.

**Matching an excerpt.** Fact-finder B's excerpt must be in a search-result
snippet from the same URL (`snippet_match`); fact-finder A's must be on its
downloaded source page (`page_match`). Either way:

- Both texts are normalised (`normalize`) and the excerpt must be a
  substring of the other. Case is kept, so matching is case-sensitive: the
  spec normalises only whitespace and quotation marks, and the excerpt is
  meant to be copied word for word.
- Quotation marks and ellipses at the excerpt's two ends are trimmed first.
  An excerpt left shorter than 20 characters or 3 words never matches: a
  year or a name is on almost any page, so it proves nothing.
- If that misses, the excerpt is looked for once more with every space
  removed from both texts (`spaceless`). So an excerpt that the search
  tool's text extraction glued together from two table cells ("Humphrey
  BogartRick Blaine") still matches the page, where Carl keeps the cells
  apart, and so does a spaced excerpt of text the page itself runs
  together. Only the spacing may differ; every other character must be the
  same.

**The same URL** (`same_page`), for B's snippets: the scheme (`http` or
`https`), the host's case, a leading `www.`, a trailing dot on the host, a
default port, a trailing slash on the path, percent-encoding in the path,
the order of the query's parameters, `utm_*` tracking parameters and the
fragment don't matter. Everything else does, including the rest of the host
(`en.m.wikipedia.org` is not `en.wikipedia.org`) and the path's case.

**The blocklist** (`blocklisted`): a suffix blocks its own domain and every
subdomain, `reddit.com` blocking `old.reddit.com` but not `notreddit.com`.
Case and trailing dots are ignored. A URL that isn't `http` or `https` with
a host (`javascript:…`, `ftp://…`, no host, unparseable) counts as
blocklisted, as `(unreadable)`: it is no citable source, and the page could
not link to it safely.

**The bands** (`band_single` for one card, `band_pair` for two). A verdict's
answer names its category and its probability sets the band: a card whose
answer isn't `supported` is never shown, whatever its p(supported). Each band
comes with one of these reason codes (`REASONS`):

- `plain:agreed`: an agreeing pair that meets the plain bar.
- `hedged:single-verified`: one card judged alone (one fact-finder working,
  or the other failed, missed the wait or found nothing) meets the hedged
  bar.
- `hedged:compatible`: the agreement call said `compatible but different`;
  each card was judged alone and the shown one meets the hedged bar.
- `hedged:agreed-below-plain`: an agreeing pair that falls short of the
  plain bar.
- `hedged:no-probabilities`: an agreeing pair, but the fact-checking model
  gave no probabilities, so hedged is the best it can be.
- `silent:claim-right`, `silent:not-found`: the fact-finders wrote no card.
- `silent:contradiction`: `claim is wrong` against `claim is right`, or the
  agreement call said `contradict`.
- `silent:mixed-outcomes`: two outcomes that can't be compared, such as
  `claim is wrong` against `question answered`.
- `silent:no-agreement`: two cards with the same outcome but no agreement
  answer, so a contradiction can't be ruled out.
- `silent:blocklisted`, `silent:unverified`, `silent:no-verdict` (the
  verdict call failed), `silent:doesnt-answer`, `silent:not-supported`,
  `silent:low-support` (p(supported) below the hedged bar): why a card
  can't be shown, checked in this order. When neither card of a pair can be
  shown, the reason is that of the card that got further down this list.

The candidate's task adds `silent:settled` (spec section 5) itself.
"""

from __future__ import annotations

import asyncio
import ipaddress
import re
import time
import unicodedata
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from html.parser import HTMLParser
from typing import Any, Literal, Protocol, TypedDict
from urllib.parse import parse_qsl, unquote, urlsplit

import httpx

from .config import Bands

# --- Normalising and matching text ----------------------------------------------

QUOTES = "\"'`´‘’‚‛“”„‟‹›«»′″ʹʺʻʼˮ＂＇〝〞"
DASHES = "‐‑‒–—―−⁃﹘﹣－"
# Soft hyphen, zero-width space, non-joiner and joiner, word joiner, byte order mark.
INVISIBLE = "\u00ad\u200b\u200c\u200d\u2060\ufeff"
_TRANSLATE = str.maketrans({c: "'" for c in QUOTES} | {c: "-" for c in DASHES} | {c: None for c in INVISIBLE}
                           | {"…": "..."})

Match = Literal["normalised", "spaceless"]


def normalize(text: str) -> str:
    """`text` in the form excerpts are matched in: Unicode NFC; every run of
    whitespace (non-breaking and thin spaces included) one space, with none
    at the ends; soft hyphens and zero-width characters removed; every
    quotation mark, apostrophe and prime `'`; every dash, hyphen and minus
    sign `-`; `…` three dots. Case is kept."""
    return " ".join(unicodedata.normalize("NFC", text).translate(_TRANSLATE).split())


# An excerpt shorter than this proves nothing: "1952" is on almost any page.
# Precision over recall.
MIN_EXCERPT_CHARS = 20
MIN_EXCERPT_WORDS = 3


def _trimmed(excerpt: str) -> str:
    """The normalised excerpt with the quotation marks and ellipses at its ends trimmed."""
    text = normalize(excerpt)
    while (trimmed := text.strip("' ").removeprefix("...").removesuffix("...")) != text:
        text = trimmed
    return text


def _too_short(text: str) -> bool:
    return len(text) < MIN_EXCERPT_CHARS or len(text.split()) < MIN_EXCERPT_WORDS


def _needle(excerpt: str) -> str:
    """The excerpt as it is looked for, or "" when it is too short to verify anything."""
    text = _trimmed(excerpt)
    return "" if _too_short(text) else text


def find_excerpt(excerpt: str, text: str) -> Match | None:
    """How `excerpt` is found in `text`: `normalised` (both normalised, the
    excerpt's ends trimmed), `spaceless` (the same with every space removed),
    or None when it isn't, or is too short (`MIN_EXCERPT_CHARS`,
    `MIN_EXCERPT_WORDS`)."""
    needle = _needle(excerpt)
    if not needle:
        return None
    haystack = normalize(text)
    if needle in haystack:
        return "normalised"
    if needle.replace(" ", "") in haystack.replace(" ", ""):
        return "spaceless"
    return None


# --- URLs and the blocklist --------------------------------------------------------

UNREADABLE = "(unreadable)"


def _host(url: str) -> str | None:
    """The lower-case ASCII host of an `http` or `https` URL, without a
    trailing dot, or None for any other URL."""
    try:
        parts = urlsplit(url.strip())
        host = parts.hostname
    except ValueError:
        return None
    if parts.scheme.lower() not in ("http", "https") or not host:
        return None
    return _ascii(host)


def _ascii(host: str) -> str:
    host = host.lower().strip(".")
    if not host.isascii():
        try:
            host = host.encode("idna").decode("ascii")
        except UnicodeError:
            pass
    return host


def _page_key(url: str) -> tuple[Any, ...] | None:
    """What two URLs of the same page share (see `same_page`), or None for an unreadable URL."""
    host = _host(url)
    if host is None:
        return None
    parts = urlsplit(url.strip())
    try:
        port = parts.port
    except ValueError:
        return None
    query = sorted((k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if not k.startswith("utm_"))
    return host.removeprefix("www."), None if port in (80, 443) else port, unquote(parts.path).rstrip("/"), query


def same_page(a: str, b: str) -> bool:
    """True if URLs `a` and `b` name the same page: they differ at most in
    scheme (`http`, `https`), the host's case, a leading `www.`, a default
    port, a trailing slash, percent-encoding in the path, the order of the
    query's parameters, `utm_*` parameters and the fragment. An unreadable
    URL is the same as nothing."""
    key = _page_key(a)
    return key is not None and key == _page_key(b)


def blocklisted(url: str, suffixes: Iterable[str]) -> str | None:
    """The blocklist suffix that `url`'s host falls under, or None.

    `reddit.com` blocks `reddit.com` and `old.reddit.com`, not
    `notreddit.com`. Case and trailing dots are ignored, in the URL and in
    the suffixes. A URL that isn't `http` or `https` with a host gives
    `UNREADABLE`: it is no citable source either.
    """
    host = _host(url)
    if host is None:
        return UNREADABLE
    for suffix in suffixes:
        s = _ascii(suffix)
        if s and (host == s or host.endswith("." + s)):
            return suffix
    return None


# --- Fact-finder B: the snippet ----------------------------------------------------


class HasSnippet(Protocol):
    """A search result as `snippet_match` reads it; `SearchResult` fits."""

    @property
    def url(self) -> str: ...

    @property
    def snippet(self) -> str | None: ...


def snippet_match(excerpt: str, url: str, results: Iterable[HasSnippet]) -> bool:
    """Fact-finder B's check: True if `excerpt` is in the snippet of a
    search result from the same page as `url` (`same_page`, `find_excerpt`)."""
    return any(r.snippet and same_page(r.url, url) and find_excerpt(excerpt, r.snippet) for r in results)


# --- Fact-finder A: the page ---------------------------------------------------------

# The same as Nominatim gets (carl.location).
USER_AGENT = "Carl (+https://github.com/akaihola/carl)"
MAX_PAGE_BYTES = 5 * 1024 * 1024
PAGE_TYPES = ("text/html", "application/xhtml+xml", "text/plain")
_META_CHARSET = re.compile(rb"""<meta[^>]+charset\s*=\s*["']?\s*([\w.:-]+)""", re.I)


class _PageText(HTMLParser):
    """A page's text, without scripts, styles and templates. Each edge of a
    block-level element becomes a line break, so table cells, list items and
    paragraphs don't run together; inline tags add nothing, so a word split
    by `<b>` or `<a>` stays whole."""

    SKIP = frozenset({"script", "style", "template"})
    BLOCK = frozenset({
        "address", "article", "aside", "blockquote", "br", "caption", "dd", "details", "dialog", "div", "dl",
        "dt", "fieldset", "figcaption", "figure", "footer", "form", "h1", "h2", "h3", "h4", "h5", "h6",
        "header", "hr", "li", "main", "nav", "ol", "option", "p", "pre", "section", "summary", "table",
        "tbody", "td", "tfoot", "th", "thead", "title", "tr", "ul",
    })

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skipping = 0

    def handle_starttag(self, tag: str, attrs: Any) -> None:
        if tag in self.SKIP:
            self.skipping += 1
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self.SKIP:
            self.skipping = max(0, self.skipping - 1)
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.skipping:
            self.parts.append(data)


def page_text(html: str) -> str:
    """The visible text of an HTML page, for finding an excerpt in it."""
    parser = _PageText()
    parser.feed(html)
    parser.close()
    return "".join(parser.parts)


def download_client(*, allow_private: bool = False) -> httpx.AsyncClient:
    """The HTTP client for source pages: HTTP/2, since Wikipedia's bot filter
    answers httpx's HTTP/1.1 requests with 403; the environment's proxy and
    CA settings; redirects followed; Carl's User-Agent. The pipeline shares
    one and closes it at shutdown.

    A source URL comes from a model, so every request, each redirect
    included, must go to a public address: never to the container's own
    network or its cloud's metadata service. Only tests allow private ones.
    """
    headers = {"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.1"}
    hooks = {} if allow_private else {"request": [refuse_private]}
    return httpx.AsyncClient(http2=True, follow_redirects=True, headers=headers, event_hooks=hooks)


class PrivateAddress(Exception):
    pass


async def refuse_private(request: httpx.Request) -> None:
    """Refuse a request whose host is, or resolves to, anything but a public address."""
    host = request.url.host
    try:
        addresses = [ipaddress.ip_address(host)]
    except ValueError:
        infos = await asyncio.get_running_loop().getaddrinfo(host, None)
        addresses = [ipaddress.ip_address(info[4][0].split("%")[0]) for info in infos]
    if not addresses or not all(a.is_global for a in addresses):
        raise PrivateAddress(f"{host} isn't a public address")


@dataclass(frozen=True)
class PageMatch:
    """Fact-finder A's check, for the recording.

    - `reason`, when the excerpt isn't verified: `no-excerpt` (nothing to
      look for), `too-short` (too short to prove anything, see
      `find_excerpt`), `download-failed` (an unreadable URL, a host that
      isn't public, a transport error or an error status; `error` says
      which), `timeout`, `not-html` (neither HTML nor plain text;
      `content_type` says what) or `not-found`. Nothing is downloaded for
      the first two.
    - `match`, when it is: `normalised` or `spaceless` (see `find_excerpt`).
    - `status` and `content_type` as the server answered, `final_url` after
      redirects, `elapsed_s` for the download alone, `bytes_read` of the
      body (decompressed), `truncated` when the page was longer than the cap
      and only its start was searched.
    """

    verified: bool
    reason: str | None = None
    match: Match | None = None
    status: int | None = None
    content_type: str | None = None
    final_url: str | None = None
    elapsed_s: float = 0.0
    bytes_read: int = 0
    truncated: bool = False
    error: str | None = None

    def event(self) -> dict[str, Any]:
        return asdict(self)


def _decode(body: bytes, charset: str | None) -> str:
    """The body as text: in the header's charset, else a `<meta>` tag's, else UTF-8."""
    meta = _META_CHARSET.search(body[:4096])
    for encoding in (charset, meta and meta.group(1).decode("ascii", "replace"), "utf-8"):
        if encoding:
            try:
                return body.decode(encoding, errors="replace")
            except LookupError:
                continue
    return body.decode("utf-8", errors="replace")


def _search_page(excerpt: str, body: bytes, charset: str | None, media_type: str) -> Match | None:
    text = _decode(body, charset)
    return find_excerpt(excerpt, text if media_type == "text/plain" else page_text(text))


async def page_match(excerpt: str, url: str, timeout_s: float, *, client: httpx.AsyncClient | None = None,
                     max_bytes: int = MAX_PAGE_BYTES) -> PageMatch:
    """Fact-finder A's check: download `url` and look for `excerpt` on it.

    The download, redirects included, must finish within `timeout_s`, and at
    most `max_bytes` of the body are read and searched. `client` defaults to
    a `download_client()` of its own, which refuses hosts that aren't public.
    A failed download or a miss leaves the card unverified; it is never an
    error, so this never raises (except when cancelled).
    """
    excerpt_text = _trimmed(excerpt)
    if not excerpt_text:
        return PageMatch(False, "no-excerpt")
    if _too_short(excerpt_text):
        return PageMatch(False, "too-short")
    if _host(url) is None:
        return PageMatch(False, "download-failed", error="unreadable URL")
    own = client is None
    http = download_client() if client is None else client
    start = time.perf_counter()
    got: dict[str, Any] = {}  # what the server answered, for the record
    body = bytearray()
    media_type, charset = "", None

    def failed(reason: str, error: str | None = None) -> PageMatch:
        return PageMatch(False, reason, error=error, elapsed_s=time.perf_counter() - start, bytes_read=len(body),
                         **got)

    try:
        async with asyncio.timeout(timeout_s), http.stream("GET", url.strip(), timeout=timeout_s) as response:
            got.update(status=response.status_code, content_type=response.headers.get("content-type"),
                       final_url=str(response.url))
            media_type = (got["content_type"] or "").split(";")[0].strip().lower()
            charset = response.charset_encoding
            if not response.is_success:
                return failed("download-failed", f"HTTP {response.status_code}")
            if media_type not in PAGE_TYPES:
                return failed("not-html")
            async for chunk in response.aiter_bytes():
                body += chunk
                if len(body) > max_bytes:
                    got["truncated"] = True
                    del body[max_bytes:]
                    break
    except TimeoutError:
        return failed("timeout")
    except httpx.TimeoutException as e:
        return failed("timeout", type(e).__name__)
    except Exception as e:  # whatever the web does, the card just stays unverified
        return failed("download-failed", f"{type(e).__name__}: {e}"[:200])
    finally:
        if own:
            await http.aclose()
    elapsed = time.perf_counter() - start
    # Parsing a big page takes a while, so it runs off the event loop.
    match = await asyncio.to_thread(_search_page, excerpt, bytes(body), charset, media_type)
    return PageMatch(match is not None, None if match else "not-found", match, elapsed_s=elapsed,
                     bytes_read=len(body), **got)


# --- The bands ----------------------------------------------------------------------

Finder = Literal["A", "B"]

CLAIM_WRONG, CLAIM_RIGHT, ANSWERED, NOT_FOUND = "claim is wrong", "claim is right", "question answered", "not found"
OUTCOMES = (CLAIM_WRONG, CLAIM_RIGHT, ANSWERED, NOT_FOUND)
CARD_OUTCOMES = (CLAIM_WRONG, ANSWERED)
SUPPORTED, NOT_SUPPORTED, DOESNT_ANSWER = "supported", "not supported", "doesn't answer the candidate"
VERDICTS = (SUPPORTED, NOT_SUPPORTED, DOESNT_ANSWER)
SAME_FACT, COMPATIBLE, CONTRADICT = "same fact", "compatible but different", "contradict"
AGREEMENTS = (SAME_FACT, COMPATIBLE, CONTRADICT)

# Why a card can't be shown, in the order it is checked.
SILENCES = (
    "silent:claim-right", "silent:not-found", "silent:blocklisted", "silent:unverified", "silent:no-verdict",
    "silent:doesnt-answer", "silent:not-supported", "silent:low-support",
)
REASONS = (
    "plain:agreed", "hedged:single-verified", "hedged:compatible", "hedged:agreed-below-plain",
    "hedged:no-probabilities", "silent:contradiction", "silent:mixed-outcomes", "silent:no-agreement",
) + SILENCES


@dataclass(frozen=True)
class Judged:
    """One fact-finder's result for a candidate, as the bands see it.

    - `outcome`: `claim is wrong`, `claim is right`, `question answered` or
      `not found`. The last two write no draft card, and the fields below
      keep their defaults.
    - `verified`: the card's excerpt is a verified excerpt.
    - `blocklisted`: the suffix its source falls under (`blocklisted()`).
    - `verdict`: the verdict's answer, or None when there is none (the call
      failed).
    - `p_supported`: the verdict's p(supported), or None when the
      fact-checking model gave no probabilities.
    """

    finder: Finder
    outcome: str
    verified: bool = False
    blocklisted: str | None = None
    verdict: str | None = None
    p_supported: float | None = None

    def __post_init__(self) -> None:
        if self.finder not in ("A", "B"):
            raise ValueError(f"no fact-finder {self.finder!r}")
        if self.outcome not in OUTCOMES:
            raise ValueError(f"no outcome {self.outcome!r}")
        if self.verdict is not None and self.verdict not in VERDICTS:
            raise ValueError(f"no verdict {self.verdict!r}")


@dataclass(frozen=True)
class Agreement:
    """The agreement call's answer, and its p(same fact) or None when the
    fact-checking model gave no probabilities."""

    answer: str
    p_same_fact: float | None = None

    def __post_init__(self) -> None:
        if self.answer not in AGREEMENTS:
            raise ValueError(f"no agreement answer {self.answer!r}")


@dataclass(frozen=True)
class Band:
    """The band, its reason code (`REASONS`) and which fact-finder's card is
    shown, None for `none`."""

    band: Literal["plain", "hedged", "none"]
    reason: str
    shown: Finder | None = None


def _silence(card: Judged, bands: Bands) -> str | None:
    """Why `card` can't be shown judged alone, or None when it meets the hedged bar."""
    if card.outcome == CLAIM_RIGHT:
        return "silent:claim-right"
    if card.outcome == NOT_FOUND:
        return "silent:not-found"
    if card.blocklisted:
        return "silent:blocklisted"
    if not card.verified:
        return "silent:unverified"
    if card.verdict is None:
        return "silent:no-verdict"
    if card.verdict == DOESNT_ANSWER:
        return "silent:doesnt-answer"
    if card.verdict == NOT_SUPPORTED:
        return "silent:not-supported"
    if card.p_supported is not None and card.p_supported < bands.hedged_supported:
        return "silent:low-support"
    return None


def band_single(card: Judged, bands: Bands) -> Band:
    """The band for one card judged alone: hedged or nothing, never plain.

    Hedged needs a verified excerpt, a source that isn't blocklisted and a
    `supported` verdict with p(supported) ≥ `hedged_supported`; with no
    probabilities, `supported` is enough.
    """
    reason = _silence(card, bands)
    return Band("none", reason) if reason else Band("hedged", "hedged:single-verified", card.finder)


def _best(cards: Iterable[Judged]) -> Judged:
    """The card with the highest p(supported); fact-finder A's on a tie."""
    return max(cards, key=lambda c: -1.0 if c.p_supported is None else c.p_supported)


def band_pair(a: Judged | None, b: Judged | None, agreement: Agreement | None, bands: Bands) -> Band:
    """The band for a candidate from both fact-finders' results, `a` and
    `b`, None for one that failed or missed the wait, and the agreement
    call's answer, None when it wasn't made or failed.

    - One result: it is judged alone (`band_single`).
    - `claim is wrong` against `claim is right`: a contradiction, nothing.
    - A card against `not found`: the card is judged alone.
    - No card, or outcomes that can't be compared: nothing.
    - Two cards with the same outcome: the agreement call decides.
      `contradict` shows nothing. `compatible but different` judges each
      card alone. `same fact` is agreement: the shown card needs the hedged
      bar, and for plain, p(same fact) ≥ `plain_same_fact`, its own
      p(supported) ≥ `plain_supported_shown` and the other card's verdict
      `supported` with p(supported) ≥ `plain_supported_other`. The other
      card may be unverified or blocklisted. With no probabilities, an
      agreeing pair is hedged at best.

    The shown card is always one that meets the hedged bar on its own, so
    it has a verified excerpt and a source that isn't blocklisted; of two,
    the one with the higher p(supported).
    """
    if a is None or b is None:
        if a is None and b is None:
            raise ValueError("both fact-finders failed: the candidate failed, and has no band")
        return band_single(a or b, bands)  # type: ignore[arg-type]
    outcomes = {a.outcome, b.outcome}
    if outcomes == {CLAIM_WRONG, CLAIM_RIGHT}:
        return Band("none", "silent:contradiction")
    cards = [c for c in (a, b) if c.outcome in CARD_OUTCOMES]
    if not cards:
        return Band("none", "silent:claim-right" if CLAIM_RIGHT in outcomes else "silent:not-found")
    if len(cards) == 1:
        other = b if cards[0] is a else a
        return band_single(cards[0], bands) if other.outcome == NOT_FOUND else Band("none", "silent:mixed-outcomes")
    if a.outcome != b.outcome:
        return Band("none", "silent:mixed-outcomes")
    if agreement is None:
        return Band("none", "silent:no-agreement")
    if agreement.answer == CONTRADICT:
        return Band("none", "silent:contradiction")
    passing = [c for c in (a, b) if _silence(c, bands) is None]
    if not passing:
        return Band("none", max((_silence(a, bands), _silence(b, bands)), key=SILENCES.index))  # type: ignore[arg-type]
    shown = _best(passing)
    if agreement.answer == COMPATIBLE:
        return Band("hedged", "hedged:compatible", shown.finder)
    other = b if shown is a else a
    if agreement.p_same_fact is None or shown.p_supported is None:
        return Band("hedged", "hedged:no-probabilities", shown.finder)
    plain = (
        agreement.p_same_fact >= bands.plain_same_fact
        and shown.p_supported >= bands.plain_supported_shown
        and other.verdict == SUPPORTED
        and other.p_supported is not None
        and other.p_supported >= bands.plain_supported_other
    )
    return Band("plain", "plain:agreed", shown.finder) if plain else Band(
        "hedged", "hedged:agreed-below-plain", shown.finder)


# --- The words Carl adds ------------------------------------------------------------

KINDS = ("claim", "open question")
_WORDS = {
    "fi": {"claim": "Väite", "open question": "Kysymys", "tag": "Varauksin", "prefix": "Todennäköisesti:"},
    "en": {"claim": "Claim", "open question": "Question", "tag": "Hedged", "prefix": "Probably:"},
}


class CardWords(TypedDict):
    label: str
    tag: str | None
    prefix: str


def card_words(kind: str, band: str, language: str) -> CardWords:
    """The words Carl adds to a card (spec section 7), in the card language:

    - `label`: Väite or Claim for a claim, Kysymys or Question for an open
      question;
    - `tag`: Varauksin or Hedged on a hedged card, None on a plain one;
    - `prefix`: "Todennäköisesti:" or "Probably:" before a hedged card's
      fact, "" on a plain one.

    `language` is the card language's code; `fi` (or `fi-FI`) is Finnish and
    anything else English. A `none` band shows no card, so it has no words.
    """
    if kind not in KINDS:
        raise ValueError(f"no candidate kind {kind!r}")
    if band not in ("plain", "hedged"):
        raise ValueError(f"a {band!r} band shows no card")
    words = _WORDS.get(re.split(r"[-_]", language.lower(), maxsplit=1)[0], _WORDS["en"])
    hedged = band == "hedged"
    return {"label": words[kind], "tag": words["tag"] if hedged else None, "prefix": words["prefix"] if hedged else ""}


def hedged_fact(fact: str, prefix: str) -> str:
    """The fact as shown: `prefix`, a space and the fact exactly as it was
    judged, or the fact alone when there is no prefix."""
    return f"{prefix} {fact}" if prefix else fact
