# Step 6: Tracking candidates

Type: task
Status: open
Blocked by: 06

Build step 6 of the [First working Carl spec](../../first-working-carl/spec.md#14-build-order).
The spec is the source of truth. This ticket lists what the step builds and
where the spec describes it. If the step is too big for one agent session,
split it into further tickets in this folder before starting.

## What to build

- **The whole settle call** ([The settle call](../../first-working-carl/spec.md#the-settle-call)):
  - `prompts/settle.md`;
  - one small typed call on each utterance while at least one candidate is
    live (being checked, waiting for the screen, or on screen), alongside
    the decision call;
  - the decision model and its context window, but the date and time only,
    with no place;
  - only the live candidates, each by its standalone restatement. An
    on-screen candidate also shows its card's fact.
  - choices `none`, `settles Cn` for a candidate not yet on screen, and
    `agrees with Cn` or `disputes Cn` for the one on screen;
  - a choice counts from a probability of 0.5 (config);
  - it waits until the decision on every earlier utterance is known.
- **What a settle does** ([What a settle does](../../first-working-carl/spec.md#what-a-settle-does)):
  - before the card is on screen, the candidate is dropped: its checks are
    cancelled or their results thrown away, a card already sent to the page
    is withdrawn, and the recording keeps `silent:settled` with the settling
    utterance's id;
  - the settling utterance goes through the decision call like any other;
  - `agrees` is recorded but shows nothing (the "Settled at the table" mark
    is the next version's);
  - `disputes` adds nothing;
  - a card in the card history never changes.
- **The cap and the timeout** ([Candidates run side by side](../../first-working-carl/spec.md#candidates-run-side-by-side)):
  - at most 8 live candidates (config). Beyond that, a new candidate fails
    with `overload`.
  - a candidate that hasn't finished 60 s after its utterance has failed
    (config), against the stage it was stuck in;
  - a candidate state for dropped.
  - Until step 7 builds the failure log, these failures go to the event log
    only.
- **Repeats of failed candidates** ([Repeats](../../first-working-carl/spec.md#repeats)):
  a repeat of a candidate that failed at a stage (a typed error, the 60 s
  timeout or `overload`) is checked as a new candidate.
- **Cards sent again after a reconnect** ([Page and server](../../first-working-carl/spec.md#page-and-server)):
  - the server is the source of truth for the session's cards;
  - after a reconnect it sends the current card and the card history again,
    and the page rebuilds its screen.
- **Example cases** for `settle.md` under `prompts/examples/`, in Finnish and
  English.

## Done when

- [ ] pytest passes in GitHub Actions on push to `main`, with fake adapters
      and no live provider calls: the settle threshold, the drop rule's
      state changes, the cap of 8, the 60 s timeout and the repeat of a
      failed candidate.
- [ ] The settle prompt's example cases have been run by hand against the
      configured model.
- [ ] Deployed and used for one session on the phone, at a real dinner or
      with a Finnish radio talk show playing beside it, with at least one
      reconnect that rebuilds the screen.
