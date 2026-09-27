# Step 1: The 2-hour connection test

Type: task
Status: open
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

- [ ] The test is run and its results are written under an `## Answer`
      heading in [ticket 02](02-step-1-skeleton-in-the-cloud.md).
- [ ] If the handover looks unworkable, or the CPU is throttled while no
      page is connected, this is raised with the owner before step 2. The
      fallback is a Scaleway Instance running the same image
      ([ADR 0002](../../../docs/adr/0002-scaleway-container-behind-a-cloudflare-loading-page.md)).
