# Step 4: A candidate's check, from finding to card

Type: task
Status: open
Blocked by: 28, 30, 31

Part of [step 4](05-step-4-first-cards.md). The
[First working Carl spec](../../first-working-carl/spec.md#candidates-run-side-by-side) is the source of truth.

## What to build

Each candidate's own task: finding → checking → ready → on screen, card
history, silent or failed. Fact-finder B, excerpt matching, the blocklist,
the verdict (`prompts/fact-checking.md`, TypeSafe Jev), the hedged band, the
card sent to the page, the restatement replacing the raw utterance in the
decision context, costs, the summary's card count, and the recording of it
all, with the times the page reports.

## Done when

- [ ] pytest covers the path from candidate to card with fake models.
