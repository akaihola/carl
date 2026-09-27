# Step 4: The fact-finding adapters

Type: task
Status: open
Blocked by: 27

Part of [step 4](05-step-4-first-cards.md). The
[First working Carl spec](../../first-working-carl/spec.md#stage-interfaces) is the source of truth.

## What to build

- The provider-neutral fact-finding interface: the candidate, its context,
  the date, time and place, and the card language in; an outcome, the
  standalone restatement and, for `claim is wrong` and `question answered`,
  a draft card (title, one-sentence fact, source URL and title, verbatim
  excerpt) out, with the search results and a call record.
- Fact-finder B: `google/gemini-3.8-flash` on Perplexity's Agent API with its
  `web_search` and a JSON schema. Fact-finder A: GPT-6 Luna with OpenAI's
  `web_search` on the Responses API. Both from the step-0 smoke test.
- Each search tool gets `user_location` as place names, never coordinates.
- Cost: tokens and search fees; Perplexity's own figure counts, and the
  difference is logged.
- `prompts/fact-finding.md` from the step-0 draft, and its example cases.

## Done when

- [ ] pytest covers both adapters against fake servers.
- [ ] The example cases have been run by hand against both.
