# Step 1: One WebSocket with a heartbeat

Type: task
Status: resolved
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

- [x] pytest covers the gate on the upgrade, the config sent at the start,
      the heartbeat when idle and not when busy, and the drop after silence.
- [x] The page stays connected through a quiet stretch, and reconnects after
      the server goes away.

## Answer

Built on 2026-09-27: `src/carl/link.py` on the server, `src/carl/web/link.js`
on the page.

- `/api/ws` is behind the gate, and a browser's upgrade must come from
  Carl's own origin (403 otherwise). Frames are capped at 1 MB.
- On connecting, the server sends `{"type": "hello", "config": …}` with the
  heartbeat, silence and handover times, the pacing and late-card times,
  and the location thresholds.
- Both sides send `{"type": "heartbeat"}` when they have sent nothing else
  for 3 s, and any frame, audio included, counts as life. After 10 s of
  silence the server closes with code 4000, and the page closes and
  reconnects after 1, 2, 4, then every 5 s. The page takes its times from
  the hello, so the config file stays their one source.
- Binary frames are counted, and used from step 2 on.
- On shutdown (a redeploy or a scale-down) the server closes every socket
  with 1001 at once, so pages reconnect without waiting out the silence.
- Checked in Chromium against a local server: 2 heartbeats sent and 3
  received in 7.5 s; after the server was stopped the page showed
  "Connection lost, reconnecting…", and it reconnected once the server was
  back.
