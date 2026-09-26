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
| Fact-checking model | TypeSafe Jev giving typed answers with probabilities, in Finnish: verdicts and the agreement call | Gemini 3.5 Flash-Lite, typed, with logprobs, called directly without grounding |

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
- [ ] API keys exist for OpenAI, Perplexity and TypeSafe, and for Google if
      the fact-checking fallback is needed. Each is in a gitignored
      `.secrets.*` file, with a hard monthly spend limit set wherever the
      provider offers one.
- [ ] The script has been run with real keys: the provisional checks, and the
      fallback of any stage whose provisional model failed.
- [ ] The results are written under an `## Answer` heading here: the summary
      table, plus a line per stage saying "confirmed" or naming the fallback
      chosen, and why.
- [ ] If a fallback is chosen, the spec's
      [Provisional models](../../first-working-carl/spec.md#provisional-models)
      table is updated, so step 1's config file starts from the right
      models.

## Comments

- 2026-09-26: Wrote the script, its cases and the draft prompts in
  [`../smoke-test/`](../smoke-test/README.md). The request shapes follow the
  vendors' docs as read on 2026-09-26. The README lists what those docs left
  open, which the first real run settles. The script was checked with a dry
  run and against mocked responses, but never against the real APIs:
  there were no keys. Next: run it with keys and record the answer.
