# fetch_url probe

A local, throwaway script for
[ticket 43](../issues/43-fetch-url-instead-of-the-source-download.md). It
measures whether Perplexity's `fetch_url` tool could stand in for Carl's own
download of fact-finder A's source page, the one that makes a **verified
excerpt** (First working Carl spec, section 6). Nothing in Carl imports it.

## Why a tool result and not the model

The excerpt check exists so that no card rests on a model's word. Asking a
model to open the page and quote it would be the model's word again. With
`fetch_url` the Agent API returns a `fetch_url_results` item holding the page
text as Perplexity's fetcher extracted it. That text comes from the fetcher,
not from the model, just as fact-finder B's search snippets do. The model
only has to call the tool, and its reply is ignored.

## What it does

For each source URL, one after the other:

1. **Carl's download:** `carl.checking.page_match` with the card's excerpt
   and the config's timeout, exactly as the pipeline runs it. Then the page
   text again without the timeout, for the depth probes.
2. **fetch_url:** one streamed Agent API call to `/v1/agent` with only
   `{"type": "fetch_url", "max_urls": 1}`, `openai/gpt-6-luna`, reasoning
   `none`, `max_steps: 1`, and the URL as the input. It is timed twice: to the
   `response.reasoning.fetch_url_results` event, which is all Carl would wait
   for, and to the end of the response. Perplexity's own cost figure is kept.

Then it checks:

- whether the card's excerpt is in each text, using Carl's `find_excerpt`.
  For fetch_url's text it also tries with the Markdown markup stripped,
  because fetch_url returns Markdown (`*italics*`, `**bold**`, links,
  numbered list items);
- **depth probes:** it takes the first dozen words of a line of Carl's page
  text at 5 %, 25 %, 50 %, 75 % and 95 % of the page's length, and looks for
  them in fetch_url's text. A page that fetch_url cut short misses its deep
  probes. The summary lists every missed probe, because most misses are
  menus, footers and sign-up boxes that the extractor leaves out on purpose.

The URLs are:

- the sources fact-finder A cites for the fact-finding example cases in
  `prompts/examples/fact-finding.toml`;
- the pages in [`pages.toml`](pages.toml). These are long pages, Finnish
  pages, and sites that turn Carl's download away. They have no excerpt, so
  only the depth probes run on them.

## Running it

From the repo root, with `OPENAI_API_KEY` and `PERPLEXITY_API_KEY` set:

    uv run .scratch/build-first-working-carl/fetch-url-probe/fetch_url_probe.py --runs 2

- `--runs N` runs fact-finder A over the cases N times, which gives more
  source pages.
- `--case ID` keeps only the cases whose id starts with `ID`.
- `--no-finder` skips fact-finder A, and `--no-pages` leaves out `pages.toml`.
- `--url URL` adds another page to probe.
- `--model` changes the model that calls `fetch_url`.

With `--runs 2` its 20 fetch calls cost about $0.025, Perplexity's own
figure on 2026-09-28. Fact-finder A's 14 calls come on top: the example
cases' file puts both fact-finders together at about $0.02 a case. A run
takes about 2 minutes.

It prints a line per URL and a summary. It writes these to
`out/<time>/`, which is kept out of git:

- `summary.md`, the summary;
- `results.jsonl`, one record per URL;
- `pages/NN-carl.txt` and `pages/NN-fetch.txt`, both texts of each page, for
  checking a miss by hand.

Timings from a Claude Code cloud session go through that session's outbound
proxy. They show neither Carl's container nor a phone's browser.
