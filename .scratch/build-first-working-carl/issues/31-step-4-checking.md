# Step 4: Excerpts, blocklist, bands and card wording

Type: task
Status: resolved
Blocked by: 

Part of [step 4](05-step-4-first-cards.md). The
[First working Carl spec](../../first-working-carl/spec.md#6-fact-finding-fact-checking-and-confidence-bands) is the source of truth.

## What to build

Pure logic, plus A's page download:

- excerpt matching: B's excerpt as a substring of a snippet from the same
  URL; A's source downloaded (about 3 s) and searched, after normalising
  whitespace and quotation marks;
- the blocklist's domain-suffix matching;
- the bands with their reason codes: hedged for step 4, plain and the pair
  rules for step 5;
- the words Carl adds in the card language: the label, the hedged tag and the
  hedge prefix.

## Done when

- [x] pytest covers each rule.

## Answer

Built on 2026-09-27: `src/carl/checking.py` and `tests/test_checking.py`
(122 tests; the whole suite passes). The item under "Done when" is met.

- **Matching excerpts.** Both texts are normalised (`normalize`): Unicode
  NFC; whitespace, non-breaking and thin spaces included, collapsed to one
  space; soft hyphens and zero-width characters removed; every quotation
  mark and apostrophe (straight, curly, „, guillemets, primes) one mark;
  every dash and the minus sign a hyphen; `…` three dots. Case is kept, so
  matching is case-sensitive, as the spec normalises only whitespace and
  quotation marks. Quotation marks and ellipses at the excerpt's ends are
  trimmed. **An excerpt then shorter than 20 characters or 3 words never
  matches** (`MIN_EXCERPT_CHARS`, `MIN_EXCERPT_WORDS`): a year or a name
  such as "1952" is on almost any page, so it proves nothing; precision over
  recall. If the excerpt misses, it is looked for once more with every space
  removed from both sides, which verifies step 0's AFI Catalog miss
  ("Humphrey BogartRick Blaine", glued from two table cells) while every
  character but spacing must still match.
  The result says which way it matched (`normalised` or `spaceless`).
  - **B** (`snippet_match`): the excerpt must be in the snippet of a search
    result from the same page. `same_page` ignores http/https, the host's
    case, `www.`, a trailing dot, default ports, a trailing slash,
    percent-encoding in the path, query order, `utm_*` parameters (OpenAI
    adds `utm_source=openai`) and the fragment; anything else, such as
    `en.m.` against `en.`, is another page.
  - **A** (`page_match`): httpx over HTTP/2 with the environment's proxy and
    CA settings, redirects followed, Carl's User-Agent, the whole download
    within the timeout (`asyncio.timeout`, not httpx's per-read one), at
    most 5 MB read (a longer page is searched up to the cap and marked
    `truncated`). HTML and plain text are searched; anything else is
    `not-html`. The text leaves out scripts, styles and templates and breaks
    lines at block-level elements (table cells included), so cells don't run
    together; parsing runs off the event loop. A `PageMatch` records
    verified, the reason (`no-excerpt`, `too-short`, `download-failed`,
    `timeout`, `not-html`, `not-found`), status, content type, final URL,
    elapsed time, bytes read, truncation and error, and it never raises.
    Nothing is downloaded for `no-excerpt` or `too-short`. The client is
    injectable (`download_client()` makes the real one).
  - **Only public addresses.** A source URL comes from a model, so
    `download_client()` refuses every request, each redirect included, whose
    host isn't a public address (`ipaddress.is_global`), whether an IP
    literal or a name looked up with `getaddrinfo` (every address it
    resolves to must be public): never this machine, the container's network
    or the cloud's metadata service. A refused request ends as
    `download-failed` with a `PrivateAddress` error. Only tests pass
    `allow_private=True`, to reach their local server. The check looks the
    name up itself, so a name that resolves differently a moment later (DNS
    rebinding) isn't caught.
  - **Live check by hand** (2 requests through the cloud environment's
    proxy): en.wikipedia.org `Casablanca_(film)` (with `?utm_source=openai`)
    and fi.wikipedia.org `Helsinki` both came back over HTTP/2 with 200,
    795 kB and 1.1 MB in 0.53 s and 0.40 s, and both excerpts were verified.
    One more request after the private-address check was added,
    `Casablanca_(film)` with the default client, was verified in 0.46 s.
- **The blocklist** (`blocklisted`): a suffix blocks its domain and every
  subdomain, ignoring case and trailing dots; `reddit.com` blocks
  `old.reddit.com`, not `notreddit.com`, and `x.com` doesn't block
  `dropbox.com`. A URL that isn't http(s) with a host (`javascript:`, none,
  unparseable) counts as blocklisted, as `(unreadable)`: it is no citable
  source and the page couldn't link to it safely.
- **The bands** (`band_single` for step 4, `band_pair` for step 5), from a
  `Judged` per fact-finder (outcome, verified, blocklisted suffix, verdict
  answer, p(supported) or None) and an `Agreement` (answer, p(same fact) or
  None). A verdict's answer names its category and its probability sets the
  band, so an answer other than `supported` is never shown. A single card
  is hedged at best. A shown card always meets the hedged bar on its own; of
  two, the higher p(supported), A on a tie. The other card of an agreeing
  pair may be unverified or blocklisted. Two cards with the same outcome but
  no agreement answer show nothing, since a contradiction can't be ruled
  out. Both finders failed raises `ValueError`: the candidate failed.
  Reason codes: `plain:agreed`, `hedged:single-verified`,
  `hedged:compatible`, `hedged:agreed-below-plain`,
  `hedged:no-probabilities`, `silent:claim-right`, `silent:not-found`,
  `silent:contradiction`, `silent:mixed-outcomes`, `silent:no-agreement`,
  `silent:blocklisted`, `silent:unverified`, `silent:no-verdict`,
  `silent:doesnt-answer`, `silent:not-supported`, `silent:low-support`. An
  exhaustive test over every combination checks the invariants.
- **Card words** (`card_words`, `hedged_fact`): the label (Väite/Claim,
  Kysymys/Question), the hedged tag (Varauksin/Hedged) and the prefix
  (Todennäköisesti:/Probably:) in the card language; `fi` (or `fi-FI`) is
  Finnish and anything else English. The hedged fact is the prefix, a space
  and the fact exactly as judged.
