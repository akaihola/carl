# Step 4: A candidate's check, from finding to card

Type: task
Status: resolved
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

- [x] pytest covers the path from candidate to card with fake models.

## Answer

Built on 2026-09-27: `src/carl/checks.py` (new), `prompts/fact-checking.md`
with its `FILLS` entry, `prompts/examples/fact-checking.toml` and `carl
examples fact-checking`, the check's hook in `decision.py`, `checks.install`
in `cli.py`, card state in `session.py` and `server.py`, `age_s` in
`docs/websocket.md`, and `tests/test_checks.py` (47 tests; the whole suite,
625, passes). The item under "Done when" is met.

- **Each candidate is its own task** (`Checker.start`, spawned with
  `Session.spawn_check`, which End waits for; End now also waits for checks
  that decisions start while it waits). No queue. `Candidate.state` moves
  `finding` → `checking` → `ready` → `on screen` → `card history`, or ends
  `silent`, `failed` or `dropped` (its card was ready only after End; a
  candidate flagged after End is dropped before any search).
- **Finding:** fact-finder B gets the candidate's kind and line, the decision
  call's own context window (`decision.context`/`line`), the place name with
  the local date, time and timezone (`Locator.place_and_time`, or the date
  and time without location), the card language by name and
  `perplexity_user_location`. The restatement goes onto the candidate at
  once, so later decision calls list the candidate by it. A `rate-limited`
  finding is tried once more after 1.5 s if the utterance ended less than
  10 s ago; any other error, or a second 429, fails the candidate.
- **Checking:** the blocklist on the source URL, `snippet_match` on B's
  results, then one verdict from Jev with `prompts/fact-checking.md`: the
  candidate's line, the same window, the card's title and fact, the excerpt
  and the local date and time. Never the restatement, the source's URL or
  its title. `band_single` gives the band; a hedged card goes to the page
  as `docs/websocket.md` shows it, with the label, tag and prefix in the
  card language.
- **The verdict is skipped** for a blocklisted or unverified card, since
  judged alone it is silent whatever the verdict says; the recording has
  `verdict skipped` with the reason code. Step 5 must ask it for every card
  of a pair, since the other card of an agreeing pair may be unverified.
- **Costs:** every call, failed ones included, is charged to the month as
  `fact-finding B` or `fact-checking` with `charged_usd` (Perplexity's and
  OpenRouter's own figures) and added to the session's cost.
- **Recording**, per candidate: `model call` (record without the request;
  B's with `attempt` and `user_location`), `finding` (outcome, restatement,
  draft card, searches, results with snippets, model), `excerpt`,
  `blocklisted`, `verdict` or `verdict skipped`, `band` with its reason
  code, `check` (final state, seconds since the utterance, error or reason)
  and `card sent`; then `card shown` and `card filed` with the page's `at`,
  `late`, the server's receive time and the card's age. The card language
  stays on the `candidate` event. **Not done:** the languages of the card
  and the excerpt; both texts are recorded, so step 8's corpus tools can
  tell them.
- **Card state on the server** (`session.Card`): each card sent with its
  state and times. `card_shown` and `card_filed` only move a card forward
  (a report arriving after a later one is recorded and changes nothing;
  `card_filed` is final). After a rejoin, when the session has any cards,
  the server sends `cards`: current (shown, not filed), waiting (utterance
  order) and history (newest first). A card ready while the page is away
  waits in the session and comes in `cards.waiting`. Every card carries
  `age_s`, the server's seconds since its utterance ended (never below 0).
- **The summary's `cards`** is the number of cards sent, or `null` when
  Carl runs without checks (no keys), so the page shows "—".
- **Example cases**, 8 (4 with a Finnish card, 2 cross-language), run twice
  against `typesafe/jev-1.13` (reported as `jev-1.13-20260917`) for about
  $0.0002 each. The step-0 prompt got 7 of 8: `fi-doesnt-answer` (a
  publication date for a claim about where the book was written) came back
  `supported` at 0.53, silent only through the 0.6 bar. `supported` now
  also asks that the fact corrects the claim or answers the question: 8 of
  8, with `fi-doesnt-answer` at 0.58 and `en-says-more` (a fact saying more
  than its excerpt) at 0.71 `not supported`, up from 0.56.
- **One live candidate** (a scratch script, MemoryStore, the real models):
  "Joo, vuonna 1956. Isä kävi katsomassa." after "Helsingissä on ollut
  olympialaisetkin." became C1 (Luna, p 0.997), B found `claim is wrong`
  with a card from olympiakomitea.fi whose excerpt matched a snippet, Jev
  said `supported` at 1.0, and the page got "Väite · Varauksin ·
  Todennäköisesti: Helsingin kesäolympialaiset järjestettiin vuonna 1952
  eikä vuonna 1956." 8.2 s after the decision call began, for $0.0087
  (decision $0.00005, B $0.0086 by Perplexity's figure, Jev $0.00003).
- **Left for step 5:** fact-finder A beside B (`judge` already returns a
  per-finder `Part`), the wait, A's page download, the agreement call,
  `band_pair`, verdicts for unverified cards of a pair. **Step 6:** the
  60 s timeout, the cap of 8, settling and withdrawn cards. **Step 7:** the
  failure log and "Can't check".
