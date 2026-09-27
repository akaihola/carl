# Step 3: Typed answers and model calls

Type: task
Status: resolved
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

- [x] pytest covers both adapters against fake servers: the request, the
      answer, the probabilities (including pooled `same as` choices), the
      cost, the estimate and each typed error.
- [x] One live call to each, run by hand, works.

## Answer

Built on 2026-09-27 in `src/carl/models/`, with `tests/test_models.py`
against fake OpenAI and OpenRouter servers on localhost. Both items under
"Done when" are met.

- **The interface** (`carl.models`): a `Question` (prompt name and version,
  the question, the choices with their descriptions, the named text fields)
  goes to `TypedModel.ask(question, stage=…)`, which returns a
  `TypedAnswer`: the answer, `probs` (None when the vendor gives none) and
  the `CallRecord`. A failure raises `ModelError(kind, record)`. Adapters
  come from `make_typed_model(stage, config, secrets, session)`, by the
  stage's provider (`openai`, `openrouter`), and share one
  `http_session()`, which honours the proxy settings. Typed calls time out
  after 20 s by default (`timeout_s`).
- **Typed prompt files** (`carl.models.questions.TypedPrompt`): read from a
  `carl.prompts.Prompt` with a `# Question` and a `# Choices` section and no
  `{placeholders}`. Its `fields` are the lower-case names in backticks
  that aren't choices; `fill(fields, ids)` fails if one is missing. A
  choice with `Cn` in it becomes one choice per id given: the same ids for
  every such choice, or a mapping for the settle call
  (`{"settles Cn": […], "agrees with Cn": ["C3"]}`). With no ids it is left
  out.
- **The call record** holds the stage, provider, the model as the provider
  reports it, prompt name and version, the fields, the stage's parameters,
  the start time, token counts, `cost_usd`, `provider_cost_usd`,
  `estimated`, `elapsed_s`, the request and response bodies (never the
  headers, so never a key), the HTTP status and, on failure, the kind, the
  provider's full error text and error code. `charged_usd` is what counts
  toward the totals: the provider's figure when it gives one.
  `ModelError`'s own message never carries the provider's text, since it can
  echo the prompt. OpenAI's 401 text echoes a masked key.
- **Errors:** `timeout`; `unavailable` for transport errors, 5xx, a run
  with status `failed`, and every 4xx except 429 (a bad key, no credits, a
  request the provider won't take: nothing came out, so nothing is bad
  output; the status and error code tell them apart); `rate-limited` for
  429; `bad output` for a 200 whose answer can't be used (not JSON, not a
  choice, a refusal, an incomplete run).
- **Cost:** from the price table per million tokens, cached tokens at the
  cached price (the input price when none is given). A call with no usage
  in its response, every timeout and transport error included, gets an
  estimate marked `estimated`: the JSON request body's characters / 4 as
  input tokens, plus the adapter's typical output (Luna 15 tokens, Jev
  45). Rejected requests are estimated too, since Carl can't know they
  weren't billed. A bad output that came with usage costs its real usage.
- **Luna** (`openai.py`): the Responses API with a strict JSON schema whose
  enum is the choices, reasoning effort, `top_logprobs` and
  `max_output_tokens` from the stage's parameters (an unknown parameter
  fails at startup), and `store: false` always, in code. The question and
  choices go in the system message, the fields as labelled text in the
  user message, as in the step-0 smoke test.
- **Probabilities from logprobs** (`logprobs.py`): read along the answer's
  tokens. The model's alternatives go to the choices they could start;
  those that could be several `same as Cn` are pooled as `same as *`,
  anything that could be other different choices is `ambiguous`, and
  anything else is `other`. The walk follows the token the model took
  while the answer could still be more than one choice, so when the answer
  is `same as C2`, the token naming the id gives `same as C1`, `same as C3`
  and so on their own probabilities. `same as *` therefore only holds mass
  when the model chose another kind of answer; then no id can be named, and
  the decision call should take the chosen answer as it is.
- **Jev** (`openrouter.py`): OpenRouter's `/api/v1/systemone` with the
  fields as `state` and one `choice` question whose `criteria` are the
  choices. Probabilities are Jev's own, and OpenRouter's `usage.cost` is
  recorded as the provider's cost.

**Live check, 2026-09-27,** through the adapters with the config file's
stages and the smoke test's prompts:

| Call | Answer | Probabilities | Tokens in / out | Carl's cost | Provider's | Time |
| --- | --- | --- | --- | --- | --- | --- |
| Luna, decision, a Finnish claim | `claim` | claim 1.00 | 536 / 13 | $0.000060 | – | 1.9 s |
| Luna, decision, a Finnish repeat of C1 | `same as C1` | same as C1 1.00 | 542 / 16 | $0.000062 | – | 0.9 s |
| Jev (`typesafe/jev-1.13-20260917`), verdict | `supported` | supported 0.99, not supported 0.01 | 638 / 45 | $0.0000268 | $0.0000268 | 0.6 s |
| Jev, agreement | `same fact` | same fact 1.00 | 503 / 44 | $0.0000211 | $0.0000211 | 0.3 s |

- A wrong key gave `unavailable (HTTP 401)` from both, with OpenAI's code
  `invalid_api_key`, each charged a small estimate.
- **Luna's logprobs are one-hot.** Asked for 20 top logprobs, it returns
  one alternative per token, the chosen one, at logprob 0, with or without
  the JSON schema and even for a vague utterance. So Luna's probabilities
  are 1.00 for its answer every time, as in step 0, and the decision
  call's thresholds in effect take the chosen answer as it is. Luna reports
  itself as `gpt-6-luna`.
- All the live calls for this ticket, exploration included, cost under
  $0.001.
