# Step 2: The dev file source

Type: task
Status: open
Blocked by: 23

Part of [step 2](03-step-2-recorder.md). The
[First working Carl spec](../../first-working-carl/spec.md#ground-rules) is the source of truth. The
WebSocket messages are in [`docs/websocket.md`](../../../docs/websocket.md).

## What to build

`carl dev-send <file>`: a local-only client that unlocks a local Carl,
starts a session and sends an audio file over the WebSocket in real time,
as the page would, converting it to 16 kHz mono PCM with ffmpeg when needed.

## Done when

- [ ] A file sent to a local server comes out as utterances in the
      recording's event log.
