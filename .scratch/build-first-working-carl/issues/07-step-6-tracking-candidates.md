# Step 6: Tracking candidates

Type: task
Status: resolved
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

- [x] pytest passes in GitHub Actions on push to `main`, with fake adapters
      and no live provider calls: the settle threshold, the drop rule's
      state changes, the cap of 8, the 60 s timeout and the repeat of a
      failed candidate.
- [x] The settle prompt's example cases have been run by hand against the
      configured model.
- [ ] Deployed and used for one session on the phone, at a real dinner or with
      Finnish talk radio or a podcast playing beside it
      ([ticket 38](38-test-material-sessions.md)), with at least one reconnect
      that rebuilds the screen.

## Answer

Built on 2026-09-27, server side (the page's `card_withdrawn` is another
ticket's): `src/carl/settle.py` (new), `prompts/settle.md` with its `FILLS`
entry, `prompts/examples/settle.toml` and `carl examples settle`, and changes
to `checks.py`, `decision.py`, `session.py`, `cli.py` and
`docs/websocket.md`, with `tests/test_settle.py` (35 tests; the whole suite,
700, passes locally, and GitHub Actions runs it on the push). The first two
items under "Done when" are met; the phone session is still to come.

- **The settle call** (`Settler`, installed with the decision call's own
  model): on each utterance, skipping backchannel, it first waits for the
  decisions still running on earlier utterances (`Session.deciding`), then
  runs only if a candidate flagged before the utterance is live (`finding`,
  `checking`, `ready` or `on screen`). It gets the decision call's context
  window, the date and time with no place, and the live candidates, each as
  `Cn: restatement` (the raw utterance until one arrives), a card on screen
  followed by `[on screen: its fact]`. Its choices are `settles Cn` for each
  live candidate not on screen, `agrees with Cn` and `disputes Cn` for the
  one on screen, and `none`. A choice counts when its own probability reaches
  `settle_threshold` (0.5); mass pooled over several ids (`settles *`) names
  no candidate and settles nothing; with no probabilities the answer is taken
  as it is. Each call is recorded (`model call`, `settle` with the outcome
  and whether it was applied) and charged as `settle`; a failed one is
  recorded as a failure and changes nothing.
- **What a settle does** (`Checker.drop`): a candidate still being checked,
  or whose card is `ready`, is `dropped` with the band `silent:settled` and
  `settled_by` the settling utterance's id. A card already sent is
  `withdrawn` with a new message, `{"type": "card_withdrawn", "id": "C3"}`,
  and left out of `cards` after a rejoin and out of the summary's count. The
  check's calls in flight aren't cancelled: they finish, are recorded and
  charged, and their results are thrown away, so nothing is left unmetered.
  A settle arriving after the card went on screen isn't applied; a card on
  screen or in the card history never changes, and a report for a withdrawn
  card is recorded but doesn't revive it. `agrees with` is recorded only.
  `disputes` adds nothing to the card, and, as the spec says, the disputing
  utterance isn't checked separately: a candidate flagged in it, before or
  after the settle call answers, is dropped as `silent:disputing`.
- **The cap:** with `max_live` (8) candidates live, a new one fails with
  `overload` before any search (recorded against `fact-finding`).
- **The timeout:** a candidate still `finding` or `checking`
  `candidates.timeout_s` (60 s) after its utterance fails with `timeout`,
  against each stage it was waiting on (`Candidate.waiting_on`: the
  fact-finders still searching, or `fact-checking`). Its calls in flight
  finish and are thrown away. A `ready` card doesn't time out; the page's
  late-card rule covers it.
- **Failures** go through one function, `Session.failure(stage, kind, …)`:
  stage, kind in the failure log's words (`bad-output`), provider, model,
  HTTP status, error code and candidate id, never conversation content. For
  now it writes a `failure` event to the recording; step 7's failure log can
  take it from there. It is called for every failed decision, settle,
  fact-finding and fact-checking call, `overload` and the timeout.
- **Repeats of failed candidates:** a `same as Cn` for a candidate that
  `failed` (a typed error, the timeout or `overload`) makes a new candidate,
  with the next id, Cn's kind and `repeat_of: Cn`, recorded as the decision
  outcome `repeat of failed`, and checked. A repeat of any other candidate
  still gets nothing.
- **Cards after a reconnect:** `cards` leaves withdrawn cards out, and isn't
  sent when nothing is left to show.
- **Example cases:** 8 (4 Finnish), run against `gpt-6-luna`. The first
  prompt got 7 of 8: `fi-agrees` ("Aivan, 1952 se tietysti oli." with the
  1952 card on screen) came back `disputes` at 0.60, the model reading
  agreement with the card as disputing the candidate's 1956. The prompt now
  says the card corrects its candidate, so agreeing with it can take the
  claim back, and that sticking to the claim against the card is disputing:
  8 of 8, each at 1.00, for $0.0004.

## Comments

- 2026-09-27: Yle Puhe, the all-talk channel this box had in mind, closed in
  January 2024, so the box now takes talk radio or a podcast.
  [Ticket 38](38-test-material-sessions.md) plans the phone sessions with
  recorded talk: its session 2 (Futucast #611) closes this box, with
  airplane mode at about 20 min for the reconnect.
