# Step 2: Sessions on the server

Type: task
Status: open
Blocked by: 20, 21, 22

Part of [step 2](03-step-2-recorder.md). The
[First working Carl spec](../../first-working-carl/spec.md#session-continuity) is the source of truth. The
WebSocket messages are in [`docs/websocket.md`](../../../docs/websocket.md).

## What to build

- `src/carl/session.py`: a session from Start to End, wiring the page's audio
  to speech-to-text and the recording, final words to utterances, and the
  stream's time to the cost meter.
- Pause: finalise, close the stream, and open a fresh one on resume with a
  "(paused)" marker. Stream boundaries start fresh speaker labels.
- End: from the page, or 2 minutes after the page's connection dropped with
  the stream kept open by keepalives. `rejoin` carries a session on after a
  reconnect.
- The recording's start event: the config file, every prompt file, the
  commit, the microphone settings and the disclosure with its text.
- Stop-and-delete, applied whenever the stop arrives, even after End.
- The "Session ended" summary and the month-to-date cost in `hello`.

## Done when

- [ ] pytest covers start, pause, resume, end, rejoin within the grace
      period, the end after it, and stop-and-delete, with the fake
      speech-to-text and an in-memory store.
