# Where a card's time goes

Type: task
Status: open
Waiting on: owner

Not part of the first working version. The owner asked on 2026-09-28 where
the time goes before a card reaches the screen, to find quick wins that cut
it without giving up precision.

## What is known

Figures already in the tickets, each measured as its ticket says:

- **The whole check.** In session `20260927T175631Z-308317`, the 9 cards
  sent took 7.0–20.3 s from the `candidate` event to `card sent`, 7 of them
  under 15 s ([ticket 43](43-audio-falls-behind-real-time.md)). The one
  live candidate with both fact-finders, on 2026-09-27, was sent 11.4 s
  after its utterance ended: B's finding at 8.3 s, A's at 8.8 s, so 2.6 s
  went between the last finding and the card
  ([ticket 06](06-step-5-second-fact-finder.md)).
- **Per stage, called alone:** the decision call 0.7–2.4 s, median 1.3 s
  ([tickets 01](01-step-0-provider-smoke-test.md) and
  [28](28-step-3-decision-call.md)); fact-finder A median 4.7 s, max
  8.6 s, and B 5.4–6.4 s (ticket 01), or A 3.7–6.9 s and B 4.2–5.7 s
  ([ticket 30](30-step-4-fact-finders.md)); A's page download 0.40–0.53 s
  ([ticket 31](31-step-4-checking.md)), capped at
  `source_download_timeout_s` (3 s); Jev 0.2–0.6 s (ticket 01).
  Speech-to-text closes a segment up to `max_endpoint_delay_ms` (1500 ms)
  after speech ends; that wait was never measured.
- Ticket 43 found that the audio arrives behind real time, which adds a
  growing delay before the decision call. That is its own ticket.

## Cost writes on the way to a card

Read in the code on 2026-09-28: every model call's cost was charged with
`await session.add_cost(…)` before its result went on. `Costs.charge` wrote
the whole month's total to the bucket (`put_object`, run in a thread) and
waited for it, under one lock shared by every call in every session. On the
way to a card that was one write after the decision call, before the check
started; one after each fact-finder's finding, before its excerpt was
checked (A's and B's queued on the lock); and one after each verdict and
the agreement call, before the band. Decision and settle calls for later
utterances queued on the same lock. How long those writes took was never
measured.

## Next, one ticket each once this one is done

- **Fact-finder A's search context:** `search_context_size` isn't set in
  `config.toml`, so OpenAI's default (medium) applies. The live run in
  ticket 06 gave A 17,494 input tokens. Try `low`.
- **Fact-finder B's steps and search type:** with `max_steps = 2`, every
  step-0 case made two searches. Try `max_steps = 1` and `search_type =
  "fast"`.
- **The endpoint delay:** `max_endpoint_delay_ms` 1500 against about 1000,
  which may split a speaker's sentence at a pause.

`carl examples fact-finding` prints each fact-finder's median and maximum
time and how many cases came out as expected, so each setting can be
compared with the current one before a deploy. The card waits for the
slower fact-finder, so speeding up one alone gains little.

## Done when

- [x] A model call's cost no longer holds up the pipeline: it is added in
  memory at once and the month's total is written in the background, and
  still written at shutdown.
- [ ] A per-stage breakdown of one recorded session's candidates, from
  its event log (each event's `time`, each call's `started_at` and
  `elapsed_s`, the `finding` and `check` events' `after_s`): the endpoint
  wait, the decision call, the gap before the fact-finders start, each
  fact-finder, the download, the verdicts and the gap before `card sent`.
  It needs the bucket, read with the owner's key as in ticket 43.
- [ ] The same breakdown for a session recorded after the cost writes
  change is deployed, showing the gaps it removed.

## Comments

- 2026-09-28: **The cost writes are off the path to a card** (the first
  box). `Costs.charge` is now synchronous: it queues the charge and a
  background task adds it to the month's total and writes the file, like
  the failure log. Charges made during a write go out right after it; a
  month that can't be read keeps its charges queued; one that can't be
  written goes out with the next write; `Sessions.close` flushes what is
  left at shutdown. `Session.add_cost` and every `account` are
  synchronous, so nothing on the way to a card awaits the bucket. New tests
  hold every bucket write open: a decision still flags its candidate, and a
  pair check (both findings, both verdicts, the agreement call) still sends
  its plain card. Both time out against the old code (run with `src/`
  stashed), and pass now. `uv run pytest -q`: 912 passed, exit 0.
- Left for the owner: the change isn't deployed; a deploy is needed, never
  during a live session. The breakdowns (the second and third boxes) need
  the bucket read with the owner's key. This session's attempt to list the
  recordings was refused by the permission check, so the owner either
  allows it for a session or runs `carl owner tail --checks` themselves.
  The third box also needs a session recorded after the deploy.
