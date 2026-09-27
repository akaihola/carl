# The WebSocket between the page and the server

One WebSocket at `/api/ws`, behind the access pass (First working Carl spec,
[One WebSocket](../.scratch/first-working-carl/spec.md#one-websocket)).
Binary frames carry audio from the page. JSON text frames carry everything
else, each an object with a `type`. Either side ignores a `type` it doesn't
know. This page lists the messages as of build step 2.

## Always

| Direction | Message | Meaning |
| --- | --- | --- |
| both | `{"type": "heartbeat"}` | Sent when nothing else was sent for `heartbeat_s` (3 s). Hearing nothing for `silence_s` (10 s) means the connection dropped |
| server → page | `{"type": "hello", "config": {…}, "costs": {"month_usd": 1.23, "month_eur": 1.08}}` | First message on every connection: the config values the page needs, and the month-to-date cost for the Start screen (`null`s when unknown) |

## A session

| Direction | Message | Meaning |
| --- | --- | --- |
| page → server | `{"type": "start", "record": true, "disclosure": {"text": "…", "confirmed_at": "2026-09-27T18:02:11.123Z"}, "mic": {…}, "timezone": "Europe/Helsinki", "start_id": "<uuid>"}` | Tap on Start. `record` is the "Record this session" switch. `disclosure` is the exact text shown (the Finnish, a blank line, the English) and when "Everyone agreed, start recording" was tapped, or `null` without recording; without both, the server doesn't record. `mic` is `track.getSettings()`. `start_id` is the page's own id for this Start: a `start` resent after a drop carries on the session it already started instead of starting another. Sent once the microphone is open |
| server → page | `{"type": "session", "session": "<id>", "state": "listening", "recording": true}` | The session's state, after start, pause, resume, rejoin and a stop. `state` is `listening` or `paused`. `recording` is true while audio is actually being written: never while paused, never after a stop |
| page → server | binary frame | About 100 ms of raw 16 kHz 16-bit little-endian mono PCM, each chunk standing alone. Only while the state is `listening`. The server handles a connection's messages in order, so audio may follow `start` or `resume` at once; the page waits for the `session` reply instead, which loses a few hundred ms |
| server → page | `{"type": "speech"}` | Speech-to-text is hearing words, at most every 500 ms: the listening indicator's dot pulses |
| page → server | `{"type": "pause"}` / `{"type": "resume"}` | Pause taps. The page stops the microphone track on pause and opens it again on resume |
| page → server | `{"type": "end"}` | End, confirmed in the top bar, or the page being hidden for good (`pagehide`) |
| server → page | `{"type": "ended", "session": "<id>", "summary": {"listening_s": 5400.0, "cost_usd": 0.18, "cost_eur": 0.16, "recording": "kept", "cards": null, "month_eur": 1.24}}` | The session is over. `recording` is `kept`, `stopped` or `none`. `cards` is `null` until step 4 |

`pause`, `resume` and `end` carry no session id: they act on the session
this connection started or rejoined. After a reconnect the page sends
`rejoin` first.

## Reconnecting

The server keeps a session for `reconnect_grace_s` (2 minutes) after its
page's connection drops, with the speech-to-text stream kept open.

| Direction | Message | Meaning |
| --- | --- | --- |
| page → server | `{"type": "rejoin", "session": "<id>"}` | After a reconnect, the page asks to carry on with its session |
| server → page | `session` or `ended` | The session carries on, or it had already ended. The `ended` summary is `null` when the server no longer knows the session, as after a restart |

## Stopping a recording

| Direction | Message | Meaning |
| --- | --- | --- |
| page → server | `{"type": "stop_recording", "session": "<id>"}` | "Stop recording?" confirmed. The page keeps the stop in local storage until the server confirms it, and sends it again on every connection, even after the session ended |
| server → page | `{"type": "recording_stopped", "session": "<id>"}` | Everything recorded for the session is deleted and nothing more will be. The session carries on as a normal session. Every stop with a well-formed session id is confirmed, even one for a session the server no longer knows |
