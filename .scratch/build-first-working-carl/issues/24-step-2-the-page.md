# Step 2: The page: Start, disclosure and session screens

Type: task
Status: resolved
Blocked by: 

Part of [step 2](03-step-2-recorder.md). The
[First working Carl spec](../../first-working-carl/spec.md#8-the-screen) is the source of truth. The
WebSocket messages are in [`docs/websocket.md`](../../../docs/websocket.md).

## What to build

In `src/carl/web/`, plain HTML, CSS and JS modules
([The screen](../../first-working-carl/spec.md#8-the-screen), the
[screen prototype](../../first-working-carl/prototypes/the-screen/screen-prototype.html)):

- the Start screen: the big round Start button, the "Record this session"
  switch (off by default every time) and "This month ≈ €…";
- the disclosure screen with the exact text, "Everyone agreed, start
  recording", "Start without recording" and Back;
- the session screen's top bar: the listening pill (green "Listening" with a
  pulsing dot while someone speaks, amber "Paused"), the red "Recording"
  pill, Pause, and End with "End the session? Cancel / End";
- "Stop recording?", with the stop kept in local storage until the server
  confirms it;
- the "Session ended" summary, leading back to Start;
- the microphone: an AudioWorklet in its own file,
  `AudioContext({sampleRate: 16000})`, 16-bit PCM chunks of about 100 ms,
  `echoCancellation` and `noiseSuppression` off, `autoGainControl` on;
- the Screen Wake Lock for the whole session, and End on `pagehide`.

## Done when

- [x] The screens work in Chromium against a local server, landscape and
      portrait.

## Answer

Built on 2026-09-27, in `src/carl/web/`.

- `index.html` holds four screens (Start, disclosure, session, "Session
  ended") and the "Stop recording?" dialog; `app.js` shows one at a time and
  keeps the session's state; `style.css` has the prototype's dark palette,
  with landscape (L1) and portrait (P) layouts by media query.
- `mic.js` and `mic-worklet.js`: `getUserMedia` with `echoCancellation` and
  `noiseSuppression` off and `autoGainControl` on,
  `AudioContext({sampleRate: 16000})` made inside the tap, and a worklet
  that downmixes to mono and posts 1600-sample (3200-byte) little-endian
  16-bit chunks. Pause stops the track and suspends the context; resume
  reopens the microphone.
- `link.js` also keeps the hello's `costs`.
- The page sends audio only while the server's last `session` says
  `listening` (not while paused, rejoining or disconnected). On every hello
  it first resends pending stops (kept in `localStorage` under
  `carl.pendingStops` until `recording_stopped`), then `rejoin`s a running
  session. An End made while the connection is down is sent after the
  rejoin; a Pause or resume made then is squared with the server's state in
  the reply. The disclosure is sent as the Finnish text, a blank line and the
  English text, exactly as shown, without the location clause.
- The wake lock is held from Start to the end and asked for again whenever
  the page is visible; `pagehide` sends `end`.
- The current card and the card history are empty placeholders marked
  `STEP 4` in `index.html`: a right column of 30% in landscape, a bottom
  strip of 30% in portrait.
- Checked with Playwright in Chromium, with its fake microphone, against a
  throwaway mock of `docs/websocket.md` (111 checks) and against the real
  server with the fake speech-to-text (22 checks). The checks covered about
  10 frames of 3200 bytes a second, no audio while paused, the track stopped
  on Pause, the exact disclosure, the `start` fields, the speech pulse,
  rejoin, stops resent across reconnects and reloads, End with its confirm,
  End while disconnected, the summary, and `pagehide`. They ran at 900x420,
  640x360, 420x900 and 360x740, and no request left the page's origin.
