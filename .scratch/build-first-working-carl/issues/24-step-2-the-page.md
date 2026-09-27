# Step 2: The page: Start, disclosure and session screens

Type: task
Status: open
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

- [ ] The screens work in Chromium against a local server, landscape and
      portrait.
