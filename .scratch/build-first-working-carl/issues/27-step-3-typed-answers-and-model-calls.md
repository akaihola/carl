# Step 3: Typed answers and model calls

Type: task
Status: open
Blocked by: 

Part of [step 3](04-step-3-decision-model.md). The
[First working Carl spec](../../first-working-carl/spec.md#stage-interfaces) is the source of truth.

## What to build

- `src/carl/models/`: the typed-answer interface shared by the decision and
  settle calls, the verdicts and the agreement call: named text fields, one
  question and a choice of answers in; the answer and a probability per
  choice out, or no probabilities when the vendor gives none.
- The call record every call returns: model id, prompt name and version,
  the values filled in, parameters, token counts, cost (Carl's figure, the
  provider's when it gives one, and whether it is estimated) and response
  time; or a typed error (`timeout`, `unavailable`, `rate-limited`,
  `bad output`) with the provider's full error text. Adapters never retry.
- The OpenAI adapter for GPT-6 Luna (typed JSON schema, reasoning `none`,
  logprobs, `store: false`) and the OpenRouter adapter for TypeSafe Jev
  (`/api/v1/systemone`, pinned `typesafe/jev-1.13`), from the step-0 smoke
  test, which worked against both.
- Cost from the price table, and an estimate marked as such when usage is
  unknown ([Cost metering](../../first-working-carl/spec.md#11-cost-metering)).

## Done when

- [ ] pytest covers both adapters against fake servers: the request, the
      answer, the probabilities (including pooled `same as` choices), the
      cost, the estimate and each typed error.
- [ ] One live call to each, run by hand, works.
