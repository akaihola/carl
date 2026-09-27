# Step 2: Speech-to-text interface and the Soniox adapter

Type: task
Status: open
Blocked by: 

Part of [step 2](03-step-2-recorder.md). The
[First working Carl spec](../../first-working-carl/spec.md#stage-interfaces) is the source of truth. The
WebSocket messages are in [`docs/websocket.md`](../../../docs/websocket.md).

## What to build

- `src/carl/stt/`: the provider-neutral interface (`Word`, `SttEvent`,
  `SttStream`, `SpeechToText`), already sketched, and the Soniox adapter
  `stt/soniox.py`: stt-rt-v5 over its WebSocket API, `s16le` at 16 kHz mono,
  speaker diarization and language identification on, endpoint detection
  with `max_endpoint_delay_ms` from the config, `language_hints` from the
  config, manual finalise, keepalives, and typed errors.
- Soniox sends sub-word tokens. The adapter joins them into words, each with
  a speaker label, start, end and language code, and keeps the raw message
  for the recording.
- A fake adapter for tests, `stt/fake.py`, that plays scripted events.

## Done when

- [ ] pytest covers token-to-word joining, endpoints, finalise, keepalive
      and errors against a fake Soniox server, with no live calls.
- [ ] One short live check against Soniox, run by hand, works.
