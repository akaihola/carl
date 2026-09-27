# Step 2: Recorder

Type: task
Status: open
Blocked by: 02, 20, 21, 22, 23, 24, 25, 26

Build step 2 of the [First working Carl spec](../../first-working-carl/spec.md#14-build-order).
The spec is the source of truth. This ticket lists what the step builds and
where the spec describes it. This step is probably too big for one agent
session. Split it into further tickets in this folder before starting.

Recording starts here. Once the disclosure screen, the recording mark and the
one-way stop-and-delete work, real dinners can be recorded. They supply audio
for later replays and don't test Carl's cards
([Ground rules](../../first-working-carl/spec.md#ground-rules)).

## What to build

- **Microphone → server → Soniox** ([Audio and utterances](../../first-working-carl/spec.md#4-audio-and-utterances)):
  - an AudioWorklet in its own JS file, `AudioContext({sampleRate: 16000})`,
    sending raw 16-bit mono PCM in chunks of about 100 ms as binary frames;
  - `echoCancellation` and `noiseSuppression` off, `autoGainControl` on, and
    `track.getSettings()` sent to the server;
  - a speech-to-text adapter behind the provider-neutral interface
    ([Stage interfaces](../../first-working-carl/spec.md#stage-interfaces)).
    Every word carries a speaker label, start, end and language code.
  - Soniox stt-rt-v5 with `s16le`, endpoint detection with
    `max_endpoint_delay_ms` 1,500 (config), and `language_hints: [fi, en]`.
- **Utterance splitting** ([From final segments to utterances](../../first-working-carl/spec.md#from-final-segments-to-utterances)):
  - split a final segment at every speaker change;
  - merge runs of 2 words or fewer between runs by the same speaker;
  - split an utterance longer than about 30 s at the next sentence end.
- **Recording** ([What a recording keeps](../../first-working-carl/spec.md#what-a-recording-keeps)),
  written under `recordings/<id>/` while the session runs:
  - audio exactly as sent to Soniox, in objects of about one minute;
  - a JSONL event log flushed about every 10 s, holding:
    - at session start: the config file, every prompt file, the git commit,
      the microphone settings, and the disclosure confirmation with its text;
    - every speech-to-text event, interim ones included, with Soniox's raw
      tokens, speaker labels and language tags;
    - Pause, End and the gaps.
- **The Start screen** ([The Start screen](../../first-working-carl/spec.md#the-start-screen)):
  - the round Start button;
  - the "Record this session" switch, off by default every time;
  - "This month ≈ €…".
  - The Location switch comes with step 3.
- **The disclosure screen** ([Starting one](../../first-working-carl/spec.md#starting-one),
  [The disclosure text](../../first-working-carl/spec.md#the-disclosure-text)):
  - the exact Finnish and English text;
  - "Everyone agreed, start recording", "Start without recording" and Back;
  - confirmed every time.
  - Location isn't collected until step 3, so until then the location clause
    is left out.
- **The session screen's first pieces:**
  - the top bar with the listening indicator (green "Listening" with a
    pulsing dot while someone speaks, amber "Paused");
  - the red "Recording" pill, shown only while audio is actually written;
  - Pause, and End with its "End the session? Cancel / End" confirmation;
  - the Screen Wake Lock for the whole session.
- **Stop-and-delete** ([Stopping a recording](../../first-working-carl/spec.md#stopping-a-recording)):
  - tapping the Recording pill opens "Stop recording?";
  - confirming deletes all of `recordings/<id>/` at once and carries on as a
    normal session;
  - the stop is one-way;
  - the cost summary keeps one line, "recording stopped and deleted at hh:mm";
  - a stop made while the connection is down is resent on reconnect, or
    kept in local storage and sent the next time Carl opens.
- **Pause** ([The speech-to-text stream](../../first-working-carl/spec.md#the-speech-to-text-stream)):
  - the page stops the microphone track and tells the server;
  - the server sends Soniox's manual finalise and closes the stream, then
    opens a new one on resume, with fresh speaker labels and a "(paused)"
    marker;
  - the heartbeat keeps the link open while paused.
- **End and the 2-minute reconnect grace period** ([Session continuity](../../first-working-carl/spec.md#session-continuity)):
  - the page sends End on `pagehide` when it can;
  - otherwise the server keeps the session, and the Soniox stream with
    keepalives, for 2 minutes waiting for the page, then ends it.
  - Until step 7 builds the handover, this grace period covers Scaleway's
    60-minute cut, and the second or two lost is marked as a gap.
- **Speech-to-text cost metering** ([Cost metering](../../first-working-carl/spec.md#11-cost-metering)):
  - stream time, counting the grace period and not Pause;
  - the month-to-date total in `costs/`, by Europe/Helsinki calendar month,
    stored in USD and shown as ≈€ at the config rate.
- **The "Session ended" summary:** the listening time, the cost and whether
  the recording was kept. Its card count shows from step 4 on.
- **The owner script's `list`, `export <id>` and `delete <id>`**
  ([The owner-only script](../../first-working-carl/spec.md#the-owner-only-script)).
  `export` joins the audio into one WAV file.
- **The dev file source:** a local-only way to send an audio file over the
  WebSocket instead of the microphone. It is not the replay and scoring
  harness.

## Leaves working

Dinners recorded, with no checks yet.

## Done when

- [x] pytest passes in GitHub Actions on push to `main`, with fake adapters
      and no live provider calls: utterance splitting and the
      speech-to-text cost maths.
- [ ] Deployed and used for one recording session on the phone, at a real
      dinner or with a Finnish radio talk show playing beside it.
- [ ] `export` of that session gives a playable WAV and the event log, and
      `delete` removes it.
- [ ] The step-2 early check is written under an `## Answer` heading here:
      Android Chrome for 2 hours with the AudioWorklet at 16 kHz, the wake
      lock, the microphone kept, heat and battery.
- [ ] After the first recorded dinner, a note here on how Soniox did at a
      real table: Finnish, code-switching, and speaker attribution at
      1–2 m. It gates nothing.

## Comments

- 2026-09-27: Split into sub-tickets: [20](20-step-2-speech-to-text-and-soniox.md)
  speech-to-text and Soniox, [21](21-step-2-utterance-splitting.md) utterance
  splitting, [22](22-step-2-recording-and-costs.md) recording and costs,
  [23](23-step-2-sessions.md) sessions on the server,
  [24](24-step-2-the-page.md) the page,
  [25](25-step-2-owner-script.md) the owner script and
  [26](26-step-2-dev-file-source.md) the dev file source. The WebSocket
  messages are in [`docs/websocket.md`](../../../docs/websocket.md).
- 2026-09-27: Sub-tickets 20–26 are resolved, CI passes on every push, and
  the step is deployed on `faktat.vempai.men` (image `558c6b7`, with every
  later step's code). Dress rehearsals from the owner's cloud environment
  played recorded speech into a local server and into the deployed one,
  and `carl owner` exported, generated and deleted those recordings. What's
  left is the owner's: a recording session on the phone, its `export` and
  `delete`, the Android 2-hour check and the Soniox note.
