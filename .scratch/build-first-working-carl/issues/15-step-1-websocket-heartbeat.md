# Step 1: One WebSocket with a heartbeat

Type: task
Status: open
Blocked by: 12, 13, 14

Part of [step 1](02-step-1-skeleton-in-the-cloud.md). The
[First working Carl spec](../../first-working-carl/spec.md#one-websocket) is
the source of truth.

## What to build

- one WebSocket at `/api/ws`, behind the access-pass gate, so it skips the
  Worker ([Hosting](../../first-working-carl/spec.md#hosting));
- binary frames for audio and JSON text frames for everything else. Until
  step 2, the server only counts the audio it gets;
- a heartbeat every 3 s (config) each way when nothing else was sent;
- 10 s (config) without any message from the other side means a dropped
  connection, on both sides. The page then shows it and reconnects. The
  "Can't hear" wording and the 2-minute grace period come with steps 2 and 7;
- at session start, the server sends the page the config values the page
  needs itself: the heartbeat and silence times, the pacing and late-card
  times, the handover time and the location thresholds.

## Done when

- [ ] pytest covers the gate on the upgrade, the config sent at the start,
      the heartbeat when idle and not when busy, and the drop after silence.
- [ ] The page stays connected through a quiet stretch, and reconnects after
      the server goes away.
