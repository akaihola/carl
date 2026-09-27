# Step 1: The 2-hour connection test

Type: task
Status: resolved
Blocked by: 18

Part of [step 1](02-step-1-skeleton-in-the-cloud.md). It is the step-1 row of
[Early checks](../../first-working-carl/spec.md#early-checks).

## What to do

Hold a WebSocket through Cloudflare's proxy to the container for 2 hours and
measure:

- where Scaleway really cuts it (the spec assumes 60 minutes);
- whether the container's CPU is throttled while no page is connected: a
  task started on the server keeps a steady pace, or not, after its page
  goes away;
- the cold start time: from the first request to a scaled-to-zero container
  until `/api/health` answers, and how much of it is Scaleway's own start.

## Done when

- [x] The test is run and its results are written under an `## Answer`
      heading in [ticket 02](02-step-1-skeleton-in-the-cloud.md).
- [x] If the handover looks unworkable, or the CPU is throttled while no
      page is connected, this is raised with the owner before step 2. The
      fallback is a Scaleway Instance running the same image
      ([ADR 0002](../../../docs/adr/0002-scaleway-container-behind-a-cloudflare-loading-page.md)).

## Comments

- 2026-09-27: Run from the owner's cloud environment with
  [`connection_test.py`](../connection-test/connection_test.py); the
  results are in [ticket 02's Answer](02-step-1-skeleton-in-the-cloud.md#answer).
  Scaleway cuts at exactly 60 minutes, the CPU isn't throttled with no page
  connected, and a cold start takes about 5 s. Nothing needed raising with
  the owner, so no fallback.
