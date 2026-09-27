# Step 2: Speech-to-text interface and the Soniox adapter

Type: task
Status: resolved
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

- [x] pytest covers token-to-word joining, endpoints, finalise, keepalive
      and errors against a fake Soniox server, with no live calls.
- [x] One short live check against Soniox, run by hand, works.

## Answer

Built on 2026-09-27: `src/carl/stt/soniox.py`, `src/carl/stt/fake.py`,
`tests/test_soniox.py` and `tests/test_stt_fake.py`. The interface in
`src/carl/stt/__init__.py` is unchanged.

- **The config frame** sends `model` from the stage, `audio_format:
  "pcm_s16le"` (Soniox's name for Carl's `s16le`), `sample_rate: 16000`,
  `num_channels: 1`, speaker diarization and language identification on,
  and `language_hints` from `open()`'s languages. The stage's params come
  next and can override those three. Carl's param names (`language_hints`,
  `enable_endpoint_detection`, `max_endpoint_delay_ms`) are Soniox's own.
- **Control frames:** `{"type": "keepalive"}`, `{"type": "finalize"}`, and
  an empty frame for close. An empty audio chunk is never sent, since it
  would end the stream.
- **Tokens to words:** a token starting with a space starts a word, and
  punctuation carries on the word before it. A change of speaker or
  language doesn't split a word. Every new word in the live check started
  with a space, even after `<end>` and at language switches, and the one
  adjacent speaker change was mid-word ("F", "inn" by speaker 3, "ish" by
  speaker 2). A word takes its first token's speaker and language. A word's
  final tokens are held back, shown as an interim word, until a later final
  token or a marker ends it, so no final word comes out twice or in part.
  Each Soniox response is one `SttEvent`, with its raw message kept.
- **`<end>` and `<fin>`** both set `endpoint`. Neither is a word. Final
  tokens after a marker in the same response wait for the next one, so an
  endpoint covers exactly the final words so far.
- **Errors** (branching on `error_type`): `limit_exceeded` and the three
  balance and budget errors (402) are `rate-limited`. `request_timeout`
  (408) is `timeout`. Anything else from Soniox, a refused connection or a
  drop is `unavailable`, and a 429 at the handshake is `rate-limited`.
  Frames that aren't JSON, binary frames and malformed tokens are
  `bad output`. A missing pong (10 s heartbeat) is `timeout`, and so is no
  `finished` within 10 s of close. An error frame comes out as a last event,
  with any held words flushed, and then as the `SttError`, whose detail
  starts with the code and type.
- **The fake** (`FakeSpeechToText`) plays scripted events, keeps the audio
  it gets and counts keepalives. Finalize adds an endpoint event and close
  adds `finished`.

Live check, run by hand on 2026-09-27. It used LibriVox public-domain
audio: 35 s of Juhani Aho's *Helsinkiin* in Finnish, 22 s of silence with
keepalives, then 35 s of *Finnish Legends* in English. After that came
finalize and close. The stream time was about 95 s.

- The stream opened in 0.5 s and gave 282 events, 136 final words and 12
  endpoints. `<fin>` came as its own event, then `finished`. Replaying the
  raw responses through the joiner gave exactly Soniox's final text.
- Languages switched at sentence boundaries ("www.tuija.tv:" en,
  "Helsingin." fi). The English intro of the Finnish recording was tagged
  en.
- Speaker labels were "1", "2" and "3" for 2 readers, and flipped within
  one reader's sentences. Real-time diarization is noisy, as Soniox warns.
- Final words lagged continuous speech by about 2–5 s. After a pause, the
  endpoint came within about 1.5–2 s.
- Soniox finalises nothing while no audio arrives. Words said just before
  the silence became final only when audio resumed.
- Soniox answers each keepalive with a response. It also answers WebSocket
  pings: in a separate run, 14 s without a frame from it passed with no
  heartbeat timeout.
- Markers come with `start_ms` and `end_ms` of 0, and with no speaker or
  language.
