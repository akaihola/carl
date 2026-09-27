# Step 2: The dev file source

Type: task
Status: resolved
Blocked by: 23

Part of [step 2](03-step-2-recorder.md). The
[First working Carl spec](../../first-working-carl/spec.md#ground-rules) is the source of truth. The
WebSocket messages are in [`docs/websocket.md`](../../../docs/websocket.md).

## What to build

`carl dev-send <file>`: a local-only client that unlocks a local Carl,
starts a session and sends an audio file over the WebSocket in real time,
as the page would, converting it to 16 kHz mono PCM with ffmpeg when needed.

## Done when

- [x] A file sent to a local server comes out as utterances in the
      recording's event log.

## Answer

Built on 2026-09-27 in `src/carl/devsource.py`, with tests in
`tests/test_devsource.py`.

```
uv run carl dev-send talk.wav [--url http://127.0.0.1:8080] [--pass PASS]
                              [--record] [--speed 1] [--pause-at SECONDS]
```

- **Local only:** the URL's host must be `localhost`, `127.0.0.1` or `::1`
  (scheme http or https), or it refuses before anything else.
- **The pass:** `--pass`, or else the first `label: pass` line of the
  gitignored `.secrets.access-passes.txt` at the repo root. It is never
  printed, not even in an error.
- **As the page does it:** POST `/api/unlock`, the `carl_pass` cookie
  copied into the jar by hand (it is Secure and a local Carl is plain http),
  `/api/ws` opened with Carl's own origin as `Origin`, `hello`, then
  `start` with `mic: {"source": "dev-send", "file": <name>}` and the
  system's IANA time zone (`TZ`, or `/etc/localtime`, or UTC). With
  `--record` the disclosure is `{"text": "dev-send: <name>", "confirmed_at":
  <now>}`. The audio goes as 3,200-byte binary frames (100 ms), one every
  100 ms / `--speed`, on a fixed schedule so a long file doesn't drift.
  A heartbeat goes whenever nothing else went for the `heartbeat_s` the
  hello names (3 s). Then `end`, and it prints the `ended` summary and the
  session id. A `speech` pulse prints a dot.
- **`--pause-at S`:** at the first frame from S seconds on, it sends
  `pause`, waits 2 s / `--speed` with the heartbeat going, sends `resume`
  and carries on with the rest of the file (nothing of the file is lost).
- **Ctrl-C** sends `end` before quitting, so the session ends at once
  instead of after the 2-minute grace period.
- **Audio:** a 16-bit PCM WAV file at any rate and channel count is read
  with `wave`, its channels averaged, and resampled to 16 kHz by linear
  interpolation in integer maths (no low-pass filter first: fine for speech
  in a dev aid). A 16 kHz mono file goes through byte for byte. About 1 s
  per minute of 48 kHz stereo. Anything else, 8-, 24-bit and float WAV
  included, goes through `ffmpeg -f s16le -ac 1 -ar 16000` if it is on
  PATH, or fails with an error saying so.
- **Tests** run the client against a real local aiohttp server with the
  scripted speech-to-text and the in-memory store: speech-to-text gets
  exactly the file's PCM (plus the silence the server adds before a
  finalise), a pause splits it across two streams, a recorded run's audio
  objects join to exactly the PCM, and its event log holds the start event
  with the disclosure, mic and time zone, the pause and resume, one
  utterance per stream and the session end. Also: a pause twice the
  server's `silence_s` survives on heartbeats, a wrong pass and no server
  are clear errors, the WAV reading, downmix and resampling (a 44.1 kHz
  stereo tone comes out as the same tone at 16 kHz), ffmpeg through a fake
  on PATH, the local-only check and the pass file.
- Not yet run against a live `carl serve` with Soniox: that needs the
  owner's key.

## Comments

- 2026-09-27: Run live: 35 s of a Finnish LibriVox reading (with its English
  preamble) sent with `--record --pause-at 15` to a local `carl serve` with
  real Soniox. The recording held both audio objects, the start event with
  the config, prompts, disclosure and microphone, and six utterances, each
  word tagged `en` or `fi` correctly, with the pause splitting the stream in
  two. It cost $0.0012.
