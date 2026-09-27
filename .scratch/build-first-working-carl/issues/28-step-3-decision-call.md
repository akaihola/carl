# Step 3: The decision call

Type: task
Status: open
Blocked by: 23, 27

Part of [step 3](04-step-3-decision-model.md). The
[First working Carl spec](../../first-working-carl/spec.md#5-decision-repeats-and-settling) is the source of truth.

## What to build

- `prompts/decision.md` from the step-0 draft, and its example cases under
  `prompts/examples/` with a script that runs them by hand.
- One decision call per utterance, each running to the end; the backchannel
  skip; the context (up to 10 earlier utterances from the last 2 minutes,
  speaker labels, "(paused)" and "(gap)" markers, place and local time, the
  session's earlier candidates C1…); the outcome from probabilities
  (repeat, candidate, none); card language
  ([Card language](../../first-working-carl/spec.md#card-language)); cost metering; and the recording
  of every call, candidate, repeat and card language.
- Candidates are recorded, not shown.

## Done when

- [ ] pytest covers the backchannel skip, the context, the repeat and
      candidate thresholds, card language and the cost, with a fake model.
- [ ] The example cases have been run by hand against the configured model.
