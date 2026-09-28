# Could Perplexity's fetch_url replace the source-page download?

Type: research
Status: resolved

Not part of the first working version. The owner asked which of Carl's
models a browser could call directly. All four APIs allow it: preflights to
the exact endpoints on 2026-09-27 answered `Access-Control-Allow-Origin: *`.
Fact-finder A's excerpt check can't move to a browser, though. The server
downloads the source page (`page_match`), and most sites send no CORS
headers. The owner then asked whether a model could download the page
instead.

A model quoting the page would be the model's word, which is exactly what
the verified excerpt must not rest on. Perplexity's Agent API has a
`fetch_url` tool whose `fetch_url_results` item returns the fetcher's
extracted text to the caller. That text can be trusted as much as fact-finder
B's search snippets. OpenAI's `web_search` never returns page text, and
OpenRouter's `openrouter:web_fetch` only documents handing it to the model.
So the question is whether `fetch_url`'s text verifies the same excerpts that
Carl's download does, how far into a long page it reaches, and how fast and
cheap it is.

## How

The [fetch_url probe](../fetch-url-probe/README.md) was run twice with
`--runs 2` on 2026-09-28, at 20:02 and 20:07 UTC, from a Claude Code cloud
session. Each run covered:

- fact-finder A's 10 cards for the 7 fact-finding example cases, with 11
  distinct source pages over both runs;
- the 10 pages in `pages.toml`.

That makes 40 `fetch_url` calls in all, through `openai/gpt-6-luna`. The
first run's code counted an empty result as `ok`, so its two empty BFI and
historia.hel.fi results are counted below as `no-content`, as the second
run's code names them. The figures come from both runs' `results.jsonl`.

## Answer

**When fetch_url returns text, it verifies the same excerpts Carl's
download does. But it returned no text for 9 of the 20 card pages, and Carl's
download got all 20.** Replacing the download would therefore leave many
cards unverified. It works better as a fallback for pages that turn Carl's
download away.

- **Agreement where there was text: 11 of 11.** `fetch_url` returned text
  for 11 of the 20 card pages. Carl verified 9 of those 11 excerpts, and
  fetch_url's text held all 9. For one of them (einstein-website.de FAQ) this
  needed the Markdown stripped, because fetch_url returns Markdown with
  `*italics*` and links. The 2 excerpts that Carl found missing were missing
  from fetch_url's text as well.
- **No text for 9 of the 20 card pages:**
  - `catalog.afi.com`, 5 times: "crawler error bad_robots_code". fetch_url
    obeys robots.txt, and Carl's download doesn't.
  - `bfi.org.uk`, 3 times: `contents: null`, "Fetched content from 0 URLs",
    with no failure marker, although the docs say one is always added.
  - `historia.hel.fi`, once: empty in the first run, 17,298 characters twice
    in the second.

  By distinct page, 2 of 11 never returned text and 1 of 11 failed once.
  Carl's download got all 20.
- **Pages that turn Carl away:** Britannica (403), olympics.com (403) and
  IMDb (an empty 202, a bot challenge) all came back through fetch_url in
  both runs, with 10,243, 4,267 and 24,495 characters. None of them was a
  card source in these runs. `kansallisbiografia.fi` failed through fetch_url
  in both runs ("broken_content_ip_block"), and Carl's download got it.
- **No length cap seen.** The longest page, English Wikipedia's Albert
  Einstein, came back at 184,019 characters, against 193,406 in Carl's text.
  It matched at every depth up to 95 %. All four long Wikipedia pages matched
  up to 75 %, and their only 95 % misses were the "last edited" footers. The
  model itself read only about 15,600 input tokens of the Einstein page, so
  the text returned to the caller is longer than what the model saw.
- **What the extractor leaves out:** mostly menus, footers, newsletter boxes
  and JavaScript notices. Two kinds of real text were lost too:
  - historia.hel.fi's opening paragraph, before the first heading (checked
    by hand in the saved texts);
  - image captions: ETH Library's photo caption, and on
    helsinginseurakunnat.fi a short standalone line that is most likely a
    caption.

  An excerpt quoting either would fail. Olympedia's missed line was a random
  "did you know" box that changes on every load.
- **Time:** `fetch_url` took these times to its `fetch_url_results` event,
  over all 40 calls:
  - median 1.6 s, p90 5.4 s, max 18.1 s;
  - 6 calls over 3 s and 4 over 8 s: two helsinginseurakunnat.fi fetches
    (13.5 s and 12.6 s), a failed kansallisbiografia.fi fetch (14.7 s), and
    Finnish Wikipedia's 1952 Olympics page (18.1 s, which took 1.3 s in the
    other run).

  To the end of the response it took median 3.0 s, p90 7.0 s and max 19.3 s.
  Carl's `page_match` took median 1.2 s, p90 1.5 s and max 2.2 s over the
  20 card pages. Reading only up to the `fetch_url_results` event saves
  about 1.4 s at the median.
- **Cost:** Perplexity's figure was $0.0473 for all 40 calls: a mean of
  $0.0012 and a maximum of $0.0033. At 10–20 candidates an hour, that is
  about 1–2.5 cents an hour.

Two things follow for a design that uses it, as observations rather than
decisions:

- A browser-only Carl would verify A's excerpts only on pages that
  Perplexity's crawler is allowed to fetch and does fetch. With every shown
  card needing a verified excerpt, that means fewer cards.
- As a fallback after Carl's own download fails (a 403 or a bot challenge),
  fetch_url would add verified excerpts. It would need a timeout of about 3 s
  to stay within the check-time budget, and `find_excerpt` would have to
  strip Markdown first.

The sample is small: 5 of the 20 card fetches were the same AFI page. A run
on the test corpus's real candidates would firm up the failure rate.

## Comments
