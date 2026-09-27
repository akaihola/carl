# Step 2: Sessions on the server

Type: task
Status: resolved
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

- [x] pytest covers start, pause, resume, end, rejoin within the grace
      period, the end after it, and stop-and-delete, with the fake
      speech-to-text and an in-memory store.

## Answer

Built on 2026-09-27 in `src/carl/session.py` and the server's `Page` in
`src/carl/server.py`.

- A session opens a speech-to-text stream at Start, sends it the page's
  audio and, in a recording session, queues the same audio for the
  recording. Final words go through the utterance splitter; each utterance
  gets Carl's id (U1, U2…) and is logged. Every raw speech-to-text message
  is logged too, interim ones included.
- The recording's first event holds the config file and its version, every
  prompt file with its version, the commit, the microphone settings, the
  disclosure with its text and the time zone. The server records only with
  a confirmed disclosure.
- Pause sends 200 ms of silence and a finalise (Soniox finalises nothing
  while no audio arrives), closes the stream and ends the current audio
  object; resume opens a fresh stream. A "(paused)" marker, or "(gap)"
  after a failed stream, is kept for step 3's context.
- A dropped page finalises the stream too, then the session waits
  `reconnect_grace_s` with keepalives every 10 s. `rejoin`, or a `start`
  resent with the same `start_id`, carries it on; otherwise it ends.
- A failed stream reopens with backoff (1, 2, 4… 30 s), while the audio
  still reaches the recording.
- The stream's open time is charged every minute and at its close; the
  month's total goes to the Start screen in `hello` and in the summary.
- A stop deletes everything recorded, whenever it arrives, even after End;
  a stop for a session the server no longer knows deletes its prefix.
- On shutdown the server ends every live session, so recordings are written
  out, then closes the sockets with 1001.
- Tested with scripted speech-to-text and an in-memory store, and run live
  with Soniox through `carl dev-send` (ticket 26).
