# Step 0: provider smoke test

A local, throwaway script for build step 0 of the
[First working Carl spec](../../first-working-carl/spec.md#14-build-order),
tracked in [ticket 01](../issues/01-step-0-provider-smoke-test.md). It calls
each text stage's provisional model, and on request its fallback, with a few
Finnish and English cases, and shows whether each does what the spec needs.
Its results confirm each provisional model or pick its fallback. Nothing in
Carl imports it.

## What it checks

| Check | Stage | Model | Role |
| --- | --- | --- | --- |
| `decision-luna` | Decision model | GPT-6 Luna, typed JSON schema, reasoning `none`, logprobs | Provisional |
| `finder-a-openai` | Fact-finder A | GPT-6 Luna with OpenAI `web_search`: Responses API, effort `none`, `tool_choice: "required"`, JSON schema, `store: false` | Provisional |
| `finder-b-perplexity` | Fact-finder B | `google/gemini-3.8-flash` pinned on Perplexity's Agent API, with its `web_search` and a JSON schema | Provisional |
| `checker-jev` | Fact-checking model | TypeSafe Jev `typesafe/jev-1.13` through OpenRouter: verdicts and the agreement call | Provisional |
| `finder-a-perplexity` | Fact-finder A | `openai/gpt-6-luna` on Perplexity's Agent API | Fallback |
| `checker-gemini` | Fact-checking model | Gemini 3.5 Flash-Lite, typed, with logprobs, no grounding | Fallback |
| `finder-b-<model>` | Fact-finder B | Any other model on Perplexity's Agent API, named with `--alt-model` | Fallback |

For each call it shows:

- whether the request was accepted with exactly these settings;
- the answer or outcome, next to the expected one from
  [`cases.toml`](cases.toml);
- for typed answers, the probability of each choice. Jev gives them natively.
  For Luna and Gemini they are read from the logprobs of the answer's first
  token, so choices that share a first token are pooled. The decision
  outcome applies the spec's thresholds (0.5) to these probabilities.
- for fact-finders:
  - the searches made and the model the provider says ran;
  - the restatement and the draft card;
  - whether the source is among the search results, and whether it is
    blocklisted;
  - whether the excerpt is verified by the spec's method for that
    fact-finder. For B, the excerpt must be a substring of a search-result
    snippet from the same URL. For A, the page is downloaded and the excerpt
    looked for in it within 3 s. The other method is shown too, for
    comparison.
- the response time and the cost. Carl's figure comes from the price table in
  the script. Perplexity's own figure is shown beside it.

It ends with a summary table, also written to `out/<time>/summary.md`.

The prompts in [`prompts/`](prompts/) are first drafts of the ones step 1
puts in Carl's `prompts/` folder. The typed prompts (`decision`,
`fact-checking` and `same-fact`) are a question plus a description for each
choice, asked about named fields:

- Jev gets the fields as its `state` object and the descriptions as its
  `criteria`.
- Luna and Gemini get the question and choices as the system message, the
  fields as labelled text, and a JSON schema that allows only the choices.

## Before running it

1. Create an API key with each provider. Set a hard monthly spend limit
   wherever the dashboard offers one
   ([Secrets](../../first-working-carl/spec.md#secrets)).
   - OpenAI: platform.openai.com.
   - Perplexity: the API settings of perplexity.ai.
   - OpenRouter, for Jev: openrouter.ai/settings/keys. Give the key a credit
     limit. OpenRouter's `/api/v1/systemone` takes TypeSafe's own request
     format at TypeSafe's price, so no TypeSafe account is needed.
   - Google AI Studio, for the fallback only. A key made there since
     2026-05-28 is an auth key and works as it is. An older standard key
     needs "Restrict to Gemini API only".
2. Put the keys in a gitignored `.secrets.*` file at the repo root, for
   example `.secrets.providers.env`:

   ```sh
   OPENAI_API_KEY=...
   PERPLEXITY_API_KEY=...
   OPENROUTER_API_KEY=...
   GEMINI_API_KEY=...
   ```

   Keys already in the environment win. A check whose key is missing is
   skipped.
3. Install [uv](https://docs.astral.sh/uv/). The script declares its own
   dependency (`httpx`), so there is nothing else to install.

## Running it

Run it from this folder:

```sh
uv run smoke_test.py                  # the four provisional checks
uv run smoke_test.py --fallbacks      # plus the fallbacks
uv run smoke_test.py --alt-model xai/grok-4.7 google/gemini-3.7-flash
                                      # try other fact-finder B models
uv run smoke_test.py --only checker-jev --cases fi-
                                      # one check, Finnish cases only
uv run smoke_test.py --list           # the checks
uv run smoke_test.py --dry-run        # write the request bodies, call nothing
```

- Perplexity's search settings can be changed with `--pplx-search-type`
  (`web`, the default, or `fast`), `--pplx-search-context` (`low`, `medium`,
  the default, or `high`) and `--pplx-max-steps` (default 2).
  - The search context sets how much snippet text comes back, and so how
    often B's excerpt can be verified.
  - At `max_steps: 1` the agent can't reason over its search results.
- The Perplexity models page lists the non-OpenAI models to try with
  `--alt-model`: `google/…`, `xai/…` and `perplexity/…` ids. Anthropic models
  are out, as the spec says.
- A run of the provisional checks costs roughly $0.10, mostly search fees.
  With the fallbacks it costs about twice that.

Every request and response is saved under `out/<time>/`, without the keys.
The folder is gitignored and stays on your computer, because it holds
providers' search results and the terms for keeping them haven't been read
yet (ticket 11).

## Reading the results

A smoke test isn't a quality evaluation. Quality is measured later, on the
test corpus. What decides each stage here:

- **The mechanics work.** The request is accepted with the spec's settings,
  the answer fits the schema, a search really ran, and Perplexity ran the
  pinned model.
- **Probabilities come back.** Without them, a decision is taken as the
  model chose it, and a fact-checking verdict can give a hedged card at best
  (spec, section 6).
- **Finnish works.** The Finnish cases get sensible answers, and the cards
  come back in the card language.
- **Draft cards are usable.** The cards are complete, their sources are
  among the search results, and a fair share of excerpts are verified.
- **Time and cost are plausible.** Carl waits about 12 s for the second
  fact-finder, and the spec estimates about $0.35–0.55 an hour.

Write the summary table and these judgements under `## Answer` in
[ticket 01](../issues/01-step-0-provider-smoke-test.md).

## Things the vendors' docs left open

These were read on 2026-09-26. The first real run, on 2026-09-27, settled
the ones it touched; see the answer in
[ticket 01](../issues/01-step-0-provider-smoke-test.md#answer).

- **Luna:** whether OpenAI's `web_search` combines with a JSON schema is not
  documented either way. Logprobs are only allowed with reasoning effort
  `none`.
- **Perplexity:**
  - The first request with a new JSON schema can take 10–30 s while
    Perplexity prepares it, so the first fact-finder B call is slow.
  - Gemini 3.8 Flash rejects reasoning effort `minimal`, so the script uses
    `low`.
  - Whether a Google model honours `web_search` and `response_format`
    together is undocumented.
- **Jev:** English is its primary language, and its docs name numbers and
  dates as weak spots. The Finnish year cases test exactly that.
- **Gemini:** the docs disagree on the structured-output field. The script
  tries `responseFormat`, then `responseJsonSchema`, then `responseSchema`,
  and reports which one worked. Its docs don't say whether 3.5 Flash-Lite
  returns logprobs.
- **Downloading sources:** Wikipedia's bot filter answers httpx's HTTP/1.1
  requests with 403 and lets HTTP/2 through, so the script uses HTTP/2.
  Fact-finder A's page download in step 5 needs the same.
