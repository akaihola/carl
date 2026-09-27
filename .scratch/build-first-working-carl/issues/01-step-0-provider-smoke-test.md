# Step 0: Provider smoke test

Type: task
Status: open
Blocked by:

Build step 0 of the [First working Carl spec](../../first-working-carl/spec.md#14-build-order).
The spec is the source of truth. Nothing is built until this step is
settled.

## What to build

A local, throwaway script that calls each text stage's provisional model with
Finnish and English inputs, and its fallback where needed. It covers the
step-0 rows of [Early checks](../../first-working-carl/spec.md#early-checks)
and the [Provisional models](../../first-working-carl/spec.md#provisional-models)
table:

| Stage | Provisional model: what is checked | Fallback |
| --- | --- | --- |
| Decision model | GPT-6 Luna with a typed JSON schema and reasoning off: answers only from the given choices, with probabilities from logprobs | With no logprobs, Carl takes the chosen answer as it is ([From probabilities to an outcome](../../first-working-carl/spec.md#from-probabilities-to-an-outcome)). TypeSafe Jev is tried later, in the comparison. |
| Fact-finder A | GPT-6 Luna with OpenAI web search: Responses API, reasoning effort `none`, `tool_choice: "required"`, JSON output, `store: false` | Luna on Perplexity's Agent API |
| Fact-finder B | `gemini-3.8-flash` pinned on Perplexity's Agent API, with Perplexity's `web_search` and a JSON schema | Another non-OpenAI model on Perplexity's Agent API with its `web_search`. As a stopgap, fact-finder A alone, which allows hedged cards only. |
| Fact-checking model | TypeSafe Jev (`typesafe/jev-1.13` through OpenRouter) giving typed answers with probabilities, in Finnish: verdicts and the agreement call | Gemini 3.5 Flash-Lite, typed, with logprobs, called directly without grounding |

For the fact-finders, the script also shows:

- whether a search really ran;
- the model the provider says ran;
- whether the draft card is complete and its source is among the search
  results;
- whether the excerpt is verified by the spec's method: B's must be a
  substring of a snippet from the same URL, and A's must be found on the
  downloaded page within 3 s
  ([Matching excerpts against their sources](../../first-working-carl/spec.md#matching-excerpts-against-their-sources));
- whether the source is blocklisted;
- the response time and the cost, with Perplexity's own figure beside
  Carl's.

## Leaves working

Each text stage's provisional model is confirmed, or its fallback chosen.

## Done when

- [x] The script is written:
      [`../smoke-test/`](../smoke-test/README.md), with Finnish and English
      cases for every check and the first drafts of the decision,
      fact-finding, fact-checking and agreement prompts.
- [ ] API keys exist for OpenAI, Perplexity and OpenRouter (for TypeSafe
      Jev), and for Google if the fact-checking fallback is needed. Each is in a gitignored
      `.secrets.*` file, with a hard monthly spend limit set wherever the
      provider offers one.
- [x] The script has been run with real keys: the provisional checks, and the
      fallback of any stage whose provisional model failed.
- [x] The results are written under an `## Answer` heading here: the summary
      table, plus a line per stage saying "confirmed" or naming the fallback
      chosen, and why.
- [x] If a fallback is chosen, the spec's
      [Provisional models](../../first-working-carl/spec.md#provisional-models)
      table is updated, so step 1's config file starts from the right
      models.

## Answer

The first run with real keys, on 2026-09-27, confirmed all four provisional
models, so no fallback was run. It ran from the owner's cloud environment,
with the prompts decision 2407e7a1, fact-checking 375b1029, fact-finding
e128c280 and same-fact c9ffa116, and Perplexity at `search_type` web,
`search_context_size` medium and `max_steps` 2. It cost about $0.10.

| Stage | Model | Role | Calls OK | As expected | Mechanics | Median / max time | Cost |
| --- | --- | --- | --- | --- | --- | --- | --- |
| decision model | gpt-6-luna (openai) | provisional | 7/7 | 7/7 | probabilities 7/7 | 1.3 s / 2.0 s | $0.00031 |
| fact-finder A | gpt-6-luna (openai) | provisional | 5/5 | 5/5 | searched 5/5, pinned model 5/5, complete cards 4/4, source in results 4/4, verified excerpt 3/4 | 4.7 s / 8.6 s | $0.05656 |
| fact-finder B | google/gemini-3.8-flash (perplexity) | provisional | 5/5 | 5/5 | searched 5/5, pinned model 5/5, complete cards 4/4, source in results 4/4, verified excerpt 3/4 | 5.9 s / 6.4 s | $0.03973 (provider $0.03974) |
| fact-checking model | typesafe/jev-1.13 (openrouter) | provisional | 8/8 | 8/8 | probabilities 8/8 | 0.2 s / 0.6 s | $0.00021 (provider $0.00021) |

- **Decision model: confirmed.** GPT-6 Luna accepted the typed JSON schema
  with reasoning effort `none` and returned logprobs. All 7 cases, 4 of them
  Finnish, came out as expected in 0.7–2.0 s. The chosen answer's
  probability was 1.00 (to two decimals) every time, so these logprobs show
  little doubt even where a person might hesitate.
- **Fact-finder A: confirmed.** OpenAI's `web_search` works together with
  the JSON schema and `tool_choice: "required"`. Every case made one search
  and got 23–39 results, the pinned model ran, and every card was complete,
  with its source among the search results, in Finnish and English alike.
  - With JSON output no `url_citation` annotations come back. Step 5 has to
    match the source against the search call's own list of sources, as this
    script does.
  - 3 of 4 excerpts were found on the downloaded page within 3 s. The miss,
    from the AFI Catalog, was glued together from two table cells
    ("Humphrey BogartRick Blaine").
  - About $0.011 per candidate, and 4–9 s.
- **Fact-finder B: confirmed.** Perplexity ran the pinned
  `google/gemini-3.8-flash` every time, and it honoured `web_search` and
  `response_format` together. Every case made two searches and got 15
  results, and every card was complete, with its source among the results.
  - The first call with the new schema took 6.2 s, not the 10–30 s the docs
    warned of.
  - 3 of 4 excerpts were verified by the spec's method, as a substring of a
    snippet from the same URL: one exactly, two after normalising whitespace
    and quotation marks. The miss, from the Finnish Wikipedia, was on the
    page but not in any snippet.
  - Perplexity's own cost figure matched Carl's: about $0.008 per candidate,
    and 5.4–6.4 s.
- **Fact-checking model: confirmed, through OpenRouter.** TypeSafe Jev runs
  as `typesafe/jev-1.13` on OpenRouter's `/api/v1/systemone`, which takes
  TypeSafe's own request format. TypeSafe serves it there at its own price:
  $0.042 per million input tokens, with output free.
  - All 8 cases came out as expected, 5 of them Finnish or mixed, including
    the two Finnish year errors. Every answer had probabilities and a
    confidence, in 0.2–0.6 s, for under $0.0001 a call.
  - The least certain was `fi-contradict` (1952 against 1948): contradict at
    0.78, with Jev's confidence at 0.67.
  - The Gemini 3.5 Flash-Lite fallback wasn't needed and wasn't run.
- **Time and cost.** Both fact-finders answered within Carl's 12 s wait
  (8.6 s at most). At 10–20 candidates an hour, fact-finder A comes to about
  $0.11–0.23 and fact-finder B to about $0.08–0.16, a little above the
  spec's $0.06–0.12. The decision model comes to about $0.03 at 600 calls,
  against the spec's $0.06. With speech-to-text, the total is about
  $0.34–0.53 an hour, inside the spec's $0.35–0.55 estimate.

## Comments

- 2026-09-26: Wrote the script, its cases and the draft prompts in
  [`../smoke-test/`](../smoke-test/README.md). The request shapes follow the
  vendors' docs as read on 2026-09-26. The README lists what those docs left
  open, which the first real run settles. The script was checked with a dry
  run and against mocked responses, but never against the real APIs:
  there were no keys. Next: run it with keys and record the answer.
- 2026-09-27: The owner put the keys in the cloud environment's variables.
  The OpenAI, Perplexity, Gemini and OpenRouter keys work. The owner chose
  to call Jev through OpenRouter rather than open a TypeSafe account, so
  `TYPESAFE_API_KEY` stays empty. Jev is pinned as `typesafe/jev-1.13`, not
  the `~typesafe/jev-latest` alias, which could change the model under
  Carl. OpenRouter's terms were added to ticket 11. Ran the provisional
  checks; the answer is above. No fallback was chosen; the spec's
  fact-checking row now names Jev's route through OpenRouter. The raw
  responses in `out/` stayed in the cloud container, which is discarded.
  Left for the owner: a hard monthly spend limit in each dashboard
  (OpenRouter's key had none on 2026-09-27), and a local `.secrets.*` file
  for runs on their own computer.
