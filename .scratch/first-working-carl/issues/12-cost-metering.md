# Metering running cost against the monthly budget

Type: grilling
Status: resolved
Blocked by: 06, 07

## Question

How is running cost measured per session and per month across all four stages (provider usage fields, price tables, estimates), where is the running total kept, how does the owner set the monthly budget, and when does the over-budget warning appear?

## Answer

Resolved by grilling with the owner (all recommendations accepted).

- **Scope.** This ticket settles metering only. Setting the **monthly budget**
  and its warning mark are ruled out of scope for this map (the first version
  excludes them, see [What "done" means](01-done-for-first-version.md#answer)).
  The product spec already fixes their behaviour, and metering keeps the
  month-to-date total a later warning compares against.
- **Where a call's cost comes from.** A **price table in the per-deploy config
  file** gives each model's rates (input, cached and output tokens, per
  search, per audio hour). Each adapter works out the call's cost from the
  provider's usage fields. When a provider also reports a cost of its own
  (e.g. Perplexity), both figures are recorded, the provider's counts toward
  the totals, and the gap is logged. The price table is part of the config
  snapshot each recording session stores.
- **Calls with unknown usage** (timeout, dropped connection, bad output
  without usage) get an **estimate**: input tokens from the request Carl sent,
  plus the stage's typical output size. The cost is marked *estimated*, never
  counted as zero or skipped.
- **What counts:** per-use charges only: speech-to-text stream time
  (including the reconnect grace period, since the stream stays open), the
  decision, fact-finding and fact-checking calls, the agreement call, and
  search fees. Fixed hosting fees are excluded. Source-page downloads are
  recorded as calls that cost 0, so their count and latency still show.
- **Months** are calendar months in Europe/Helsinki time. Each call is dated
  by its own timestamp, so a session that crosses into a new month splits
  its cost between the two months.
- **Where totals are kept:** in the small server store that also holds the
  failure log, as
  - a **per-session cost summary**: start, duration, and cost per stage split
    into actual and estimated, with no conversation content;
  - a **month-to-date total**, updated on every call.

  Both are kept indefinitely (no conversation content; the later comparison
  map wants the history). Per-call costs also go into a recording session's
  JSONL event log as before.
- **Currency:** stored in USD, as billed. Shown in € using a fixed rate from
  config, marked "≈".
- **What the owner sees:** the Start screen shows the month-to-date total and
  a line for the last session (duration, cost, €/h). Nothing about cost
  appears during a session.
- **Checking against the bills** is done by hand now and then. The owner-only
  script from [Where the card archive, failure log and recording sessions are
  kept](11-storage-expiry-deletion.md#answer) also prints month totals per
  provider, to compare with the providers' dashboards. No automatic
  reconciliation.

## Comments

- From [Provisional models for each stage](07-provisional-models.md#answer): the stages are now speech-to-text, decision, fact-finding (two in parallel, plus Perplexity per-search fees) and fact-checking (Jev bills input tokens only). Every call returns tokens, cost and latency.
- From [How audio is streamed and how speaker labels reach the decision model](08-audio-and-speaker-labels.md#answer): Soniox bills by stream duration, and the stream stays open with keepalives through the 2-minute reconnect grace period; it is closed during Pause.
- From [Splitting verdict confidence into plain, hedged and silent](10-confidence-bands.md#answer): each candidate that gets two draft cards adds a third fact-checking call (the agreement call), and the server downloads fact-finder A's source page. Both are small but should be metered.
