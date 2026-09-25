# Streaming speech-to-text for Finnish and English table audio

Research for the ticket *Streaming speech-to-text for Finnish and English
table audio*
(`.scratch/first-working-carl/issues/02-streaming-speech-to-text.md`),
compiled 2026-09-25. It builds on the vendor list in
[realtime-fact-checking.md](realtime-fact-checking.md) and uses the
vocabulary of [CONTEXT.md](../../CONTEXT.md). An **utterance** is one final
transcript segment attributed to a single speaker, so the question for each
service is how directly its output can become utterances.

## How this was researched, and how far to trust it

- Every claim comes from the vendor's own documentation, API reference,
  pricing page or launch post, read on 2026-09-25. Nothing was tested with
  real audio. The ticket asks for services "good enough to build and record
  with", and only a recording session can show accuracy on Finnish table
  audio.
- **[verified]** means the claim was read on the cited primary page.
- **[vendor]** marks self-reported performance claims (accuracy, latency,
  comparisons with competitors) that nobody has measured independently.
- **[unverified]** marks something the docs leave out or leave unclear.
  These are the open questions.
- Prices are list pay-as-you-go prices in USD per hour of audio, unless
  noted otherwise. Several vendors bill for **session time** rather than
  speech time (see each entry), which matters because a Carl session is
  mostly silence and pauses.

## Summary

1. **Only two services document all three things Carl needs together:
   Finnish, Finnish/English code-switching and streaming diarization.**
   They are **AssemblyAI Universal-3.6 Pro Streaming** and **Soniox
   stt-rt-v5**. Both are recent (Soniox v5 in June 2026, AssemblyAI 3.6 Pro
   after 3.5 Pro), and neither vendor publishes a Finnish accuracy figure.
2. **Speechmatics and Deepgram handle Finnish well on paper, but one
   language per stream.** Speechmatics Enhanced and Deepgram Nova-3 both
   support `fi` with streaming diarization. Neither has a Finnish/English
   bilingual pack. Speechmatics' code-switching model, **Melia 1**, is in a
   Realtime *preview* with no speaker diarization until "Q4 2026" and finals
   around 4 s. Deepgram's `multi` mode leaves out Finnish.
3. **Four candidates drop out for Carl as documented today:**
   - **Google Chirp 3**: diarization only in `Recognize`/`BatchRecognize`,
     not streaming, and streams are capped at 5 minutes.
   - **OpenAI `gpt-live-transcribe`**: "doesn't return … speaker labels".
   - **ElevenLabs Scribe v2 Realtime**: no diarization parameter on the
     realtime endpoint.
   - **xAI Grok Voice Transcribe 2.0**: Finnish is not on its 25-language
     list, and the STT docs say to proxy the WebSocket through a backend.
4. **Azure works but is the most expensive** at about $1.30/h with
   diarization. Its language identification switches between candidate
   languages but "doesn't support changing languages within the same
   sentence".
5. **pyannoteAI Live-1 is a credible diarizer-only add-on** (€0.198/h, up to
   8 speakers, single-use WebSocket URL a browser can open). It would let
   Carl pair a code-switching transcriber that has no diarization (OpenAI,
   ElevenLabs, Speechmatics Melia) with separate speaker labels. The cost is
   a second stream and aligning the two by timestamp.
6. **Every serious candidate lets a browser stream directly with a
   short-lived token.** Carl still needs a tiny server endpoint to mint the
   tokens, but not an audio relay. The exceptions are Google (gRPC with
   service credentials) and xAI STT (the docs say to proxy).

## Comparison

"Code-switching" means one stream transcribes both Finnish and English
without the language being chosen in advance.

| Service (model) | Finnish | fi/en code-switching | Streaming diarization | Price/h incl. diarization | Browser direct | Session cap |
| --- | --- | --- | --- | --- | --- | --- |
| Speechmatics (Enhanced / Standard) | Yes | No (no fi/en pack) | Yes, per word `S1`, `S2`…; unlimited speakers by default | $0.43 / $0.24 | Yes, temporary key as `jwt` query param | 48 h |
| Speechmatics (Melia 1 RT preview) | Yes | Yes | **Not yet** (planned Q4 2026) | Not listed (preview) | Same | – |
| Deepgram (Nova-3) | Yes (`fi`, monolingual) | No (`multi` has 10 languages, no `fi`) | Yes, v1 streaming diarizer, per-word integer `speaker` | ≈ $0.41 (0.288 + 0.12) | Yes, `/v1/auth/grant` token | Not stated; 10 s no-audio timeout |
| Google (Chirp 3) | Yes (`fi-FI`) | Auto-detects the dominant language | **No** (batch/Recognize only) | $0.96 | No, gRPC via server | 5 min per stream |
| xAI (Grok Voice Transcribe 2.0) | **Not listed** | Claims mid-recording switching [vendor] | Yes, per-word integer `speaker` | $0.20 | Docs say proxy via backend | Not stated |
| AssemblyAI (Universal-3.6 Pro Streaming) | Yes | Yes, native | Yes, per turn `speaker_label` (A, B…) plus per word; 1–10 speakers | ≈ $0.57 (0.45 + 0.12)* | Yes, temporary `token` query param | 3 h |
| Soniox (stt-rt-v5) | Yes | Yes, native | Yes, per token `speaker`; up to 15 speakers | ≈ $0.12, diarization included | Yes, temporary API keys | 300 min |
| OpenAI (gpt-live-transcribe) | Not listed [unverified] | Language hints, several allowed | **No** | $1.02 | Yes, ephemeral key (WebRTC) | 60 min |
| ElevenLabs (Scribe v2 Realtime) | Yes | Auto-detect, `secondary_languages` | **No** documented parameter | $0.39 | Yes, single-use token | Not stated |
| Azure Speech (ConversationTranscriber) | Yes (`fi-FI`) | Continuous LID, not within a sentence | Yes, `Guest-1`, `Guest-2`… | ≈ $1.30 (1.00 + 0.30) | Yes, JS Speech SDK with 10-minute STS token | 240 min for real-time diarization |
| pyannoteAI Live-1 (diarization only) | Any (no transcription) | – | Speaker start/end events; up to 8 speakers | €0.198 + plan (from €19/mo) | Yes, single-use stream URL | 5 h |

\* AssemblyAI's pricing page lists Universal-3.5 Pro Realtime at $0.45/h
and streaming diarization at $0.12/h. It does not list 3.6 Pro separately
[unverified that 3.6 costs the same].

## Candidates

### Speechmatics [verified]

- **Finnish.** `fi` is supported by the Enhanced and Standard models, which
  both run in Realtime. The bilingual packs are Arabic, Malay, Mandarin,
  Spanish, Tamil and Tagalog with English, so none covers Finnish. Enhanced
  and Standard "do not handle multilingual or code-switching scenarios".
- **Melia 1** is the code-switching model (launched in Batch on 2026-06-17).
  Its language list is the one on the languages page, which includes `fi`.
  A **Realtime preview** exists on `wss://preview.rt.speechmatics.com/v2`
  for existing customers, "for evaluation only, … not intended for
  production use", with production planned for October 2026. In the
  preview:
  - speaker diarization is "Not yet", planned Q4 2026;
  - language hints are "Not yet";
  - "Finals latency averages around 4 seconds and varies".

  The Python SDK added Melia 1 Realtime support in PR #126, merged
  2026-09-25.
- **Diarization.** Every word and punctuation object carries `speaker`
  (`S1`, `S2`… or `UU` for unknown). There is no speaker limit by default;
  `max_speakers` can be set to 2 or more. Other settings are
  `speaker_sensitivity` (0–1, default 0.5) and `prefer_current_speaker`,
  which reduces false switches between similar voices.
- **Finals and latency.** Partials arrive in under 500 ms and may change.
  Finals "are never updated" and arrive in about 0.7–2 s, set by
  `max_delay`. These are the vendor's own figures.
- **Price.** Real-time Standard $0.24/h and Enhanced $0.43/h (pricing page
  last updated 2026-07-31). The page shows no separate diarization line.
  New accounts get $100 of credit; the free tier allows 2 concurrent
  real-time sessions.
- **Browser.** Temporary keys (TTL 60–86,400 s) go in the WebSocket URL as
  `?jwt=`. The docs present this as the way for end users to connect
  directly.
- **Audio.** `raw` input as `pcm_f32le`, `pcm_s16le` or `mulaw` at a stated
  sample rate, or `file` input. Speechmatics recommends `raw`.
- **Limits.** A session ends after 48 h, after 1 h with no audio, or after
  3 min with no audio or ping/pong. For longer runs, open a new session
  before closing the old one; new sessions start "in under a second". The
  service does not retain audio or transcripts.
- **Also new:** *Linden 1*, an "Agent STT" model at $0.16/h with the same
  languages as Realtime. It was not investigated.

### Deepgram [verified]

- **Finnish.** Nova-3 lists `fi` as a monolingual language, and Nova-2 does
  too. `language=multi`, the code-switching mode, covers English, Spanish,
  French, German, Hindi, Russian, Portuguese, Japanese, Italian and Dutch,
  so not Finnish. Flux Multilingual has the same 10 languages.
- **Diarization.** Streaming uses the **v1** diarizer. The newer v2 is batch
  only, and requesting it on a stream is a validation error. Each word
  carries an integer `speaker`; streaming responses leave out
  `speaker_confidence`. No maximum speaker count is documented.
- **Finals.** `is_final: true` marks a finalised chunk of text, and
  `speech_final: true` marks the end of an utterance once `endpointing`
  milliseconds of silence have passed. The default is 10 ms; 300–500 ms is
  recommended for conversation, and 100 ms for code-switching. The docs
  publish no latency figure.
- **Price (streaming).** Nova-3 Monolingual $0.0048/min ($0.288/h, reduced
  from a regular $0.0077/min) plus diarization $0.0020/min ($0.12/h), about
  **$0.41/h** in total.
- **Browser.** `POST /v1/auth/grant` returns a JWT with a 30 s TTL (up to
  3,600 s via `ttl_seconds`). The token only has to be valid when the
  WebSocket opens. The JS SDK connects from browsers directly to
  `wss://api.deepgram.com`.
- **Audio.** Raw `linear16`, `opus` and others with `encoding` and
  `sample_rate`, or containerised audio such as WebM/Opus, which is what
  browser MediaRecorder produces.
- **Limits.** No maximum stream length is documented. The connection closes
  (NET-0001) after 10 s with no audio or `KeepAlive`. On reconnect,
  timestamps restart at zero, and the docs advise buffering audio while the
  connection is down.

### Google Cloud Speech-to-Text, Chirp 3 [verified]

- **Finnish.** `fi-FI` is GA. Setting `language_codes=["auto"]` "infers and
  transcribes in the most prevalent language", which picks one language
  rather than following switches.
- **Diarization.** "Chirp 3 supports transcription and diarization only in
  BatchRecognize and Recognize", and only for 14 locales, none of them
  Finnish. The feature table says diarization is "Available only in
  Speech.BatchRecognize". **No streaming diarization.**
- **Limits.** A `StreamingRecognize` stream stays open for at most
  **5 minutes**. Longer streams need the "endless streaming" pattern of
  reconnecting.
- **Price.** $0.016/min, or $0.96/h, for the first 500,000 min per month
  (V2 API).
- **Browser.** V2 streaming is a gRPC API with Google Cloud credentials, so
  it needs a server relay.
- **Verdict for Carl:** not a fit as a single service. The earlier note's
  suggestion to evaluate it came before this limit was known.

### xAI Grok Voice Transcribe 2.0 [verified]

- Released 2026-09-18. `grok-voice-transcribe-2.0` **is now the default**
  on both REST and WebSocket, which corrects the earlier note's claim that
  1.0 is the default.
- **Finnish.** The docs list 25 languages (Arabic … Vietnamese, including
  Swedish and Danish). **Finnish is not among them.** The docs say "the
  model transcribes speech in any of these languages". The launch post
  claims "dozens of languages" and automatic following of "mid-recording
  switches" [vendor].
- **Diarization.** Adding `diarize=true` gives words an integer `speaker`
  in partial and final events. There is no documented maximum speaker
  count.
- **Finals.** There are three states:
  - interim, sent every ~500 ms when `interim_results=true`;
  - chunk final, with the text locked after about 3 s of speech;
  - utterance final (`speech_final`), after `endpointing` ms of silence
    (default 400) or when Smart Turn decides the turn has ended.

  The docs publish no latency figure.
- **Price.** Streaming $0.20/h with diarization, timestamps and key terms
  included; batch $0.10/h.
- **Browser.** The STT page says "Always proxy WebSocket connections through
  your backend". Ephemeral tokens (`/v1/realtime/client_secrets`, usable
  through the `xai-client-secret.` WebSocket subprotocol) are documented
  for the speech-to-speech Realtime API. Whether they work on `/v1/stt` is
  [unverified].
- **Audio.** Raw PCM16 (16 kHz is native), µ-law, A-law, or raw Opus
  packets with one packet per frame. Ogg and WebM containers are not
  accepted on the stream.
- **Limits.** No session length limit is documented [unverified].

### AssemblyAI Universal-3.6 Pro Streaming [verified]

- **Finnish and code-switching.** 3.6 Pro is the default streaming model and
  "code-switches across 32 languages", **including Finnish (`fi`) and
  English**, with no configuration. `language_codes: ["fi","en"]` biases
  it toward those two, and `language_detection: true` adds a
  `language_code` to each final turn. The older 3.5 Pro (19 languages) and
  Universal-Streaming Multilingual (EN/ES/DE/FR/PT/IT) are not relevant.
- **Diarization.** With `speaker_labels: true`, every `Turn` gets a
  `speaker_label` (`A`, `B`…) for the dominant speaker plus a
  `speaker_confidence`, and each final word has its own `speaker`, so a
  speaker change mid-turn is visible. `max_speakers` is a hard cap from 1
  to 10. Short backchannels may be labelled `PENDING`. Accuracy "improves
  over the course of a session" [vendor]. Corrected labels for earlier
  turns come in `SpeakerRevision` messages, at the end of the session or at
  a set interval (minimum 2 min of audio).
- **Finals and latency.** `Turn` messages with `end_of_turn: false` are
  partials, and `end_of_turn: true` is the final formatted turn. This
  shape is the closest of any service to Carl's utterance. For 3.5 Pro,
  "time to complete turn" is P50 568 ms and P90 829 ms, measured on the
  vendor's voice-agent data [vendor].
- **Price.** Universal-3.5 Pro Realtime is $0.45/h and streaming diarization
  $0.12/h. **Billing is by session duration**: "You are billed for the full
  session duration".
- **Browser.** A temporary token (`expires_in_seconds` 1–600, optional
  `max_session_duration_seconds` 60–10,800) is passed as the `token` query
  parameter.
- **Audio.** 16 kHz 16-bit mono PCM by default in about 50 ms chunks (the
  allowed range is 50–1,000 ms per chunk). It also accepts `ogg_opus`,
  which "browser MediaRecorder" produces, raw `opus` and `aac`.
- **Limits.** 3 hours per session (close code 3008). An optional
  `inactivity_timeout` can be reset with `KeepAlive`.

### Soniox stt-rt-v5 [verified]

- **Finnish and code-switching.** 60+ languages including Finnish (`fi`).
  "By default, you don't need to pre-select a language"; the model handles
  languages "mixed within a single sentence or conversation".
  `language_hints` biases it without restricting it. v5 replaced v4 on
  2026-06-16 with "reinvented speaker separation" [vendor].
- **Diarization.** `enable_speaker_diarization: true` puts a `speaker`
  (`"1"`, `"2"`…) on each token, for up to 15 speakers. It works in all
  supported languages. Soniox itself warns that real-time diarization has
  "higher speaker attribution errors" and "temporary speaker switches", and
  that **endpoint detection and manual finalisation reduce diarization
  accuracy**. This works against Carl's need for timely final utterances.
- **Finals and latency.** Tokens are either `is_final: false` (provisional)
  or `true` (never changes). With endpoint detection, a `<end>` token
  closes a segment no later than `max_endpoint_delay_ms` after speech ends
  (500–3,000 ms, default 2,000).
- **Price.** Token-based, "about $0.12/hour" for real-time. Diarization and
  language identification are included. Input audio tokens count the
  "Duration of audio or streaming session". Soniox's comparisons with
  competitors on the same page are [vendor].
- **Browser.** Temporary API keys (`usage_type`, `expires_in_seconds`,
  optional `single_use` and `max_session_duration_seconds`), a "direct
  stream" guide for browsers, and a Web SDK (`@soniox/client`).
- **Audio.** `audio_format: "auto"`, or explicit raw formats (`s16le`,
  `f32le`…) and containers (`wav`, `ogg`, `flac`…).
- **Limits.** 300 minutes per stream, fixed. Keepalive at least every
  20 s when no audio is sent. Default concurrency is 10.

### OpenAI realtime transcription [verified]

- The recommended model is `gpt-live-transcribe`, in a Realtime session
  with `type: "transcription"`. The browser connects over WebRTC using an
  ephemeral key, or over WebSocket with an `openai-insecure-api-key.`
  subprotocol.
- **Diarization.** "`gpt-live-transcribe` doesn't return word-level
  timestamps, speaker labels, or transcription confidence scores." It
  accepts several `languages` hints. The docs do not list which languages
  it supports [unverified for Finnish].
- **Finals.** Deltas stream in, and a final transcript arrives per committed
  audio turn. The model doesn't support server VAD, so the client must
  detect the end of speech and send `commit`. A `delay` setting from
  `minimal` to `xhigh` trades latency for accuracy.
- **Price.** $0.017/min ($1.02/h). **Limit:** Realtime sessions last at most
  60 minutes.
- **Verdict:** usable only with a separate diarizer such as Live-1.

### ElevenLabs Scribe v2 Realtime [verified]

- **Finnish.** It supports 90+ languages including Finnish (`fin`), with
  auto-detection and `secondary_languages`. Partials arrive in about 150 ms
  [vendor].
- **Diarization.** The batch Scribe v2 diarizes up to 32 speakers. The
  realtime API reference has **no diarization parameter**; a `speaker_id`
  field exists in the word schema "if available" [unverified whether
  realtime ever fills it].
- **Finals.** `partial_transcript` and `committed_transcript` events, with
  commits made by VAD or manually.
- **Price.** $0.39/h. **Browser:** a single-use token (`realtime_scribe`)
  that expires after 15 minutes. **Audio:** PCM at 8–48 kHz, or µ-law. No
  session cap is documented.

### Azure AI Speech, ConversationTranscriber [verified]

- **Finnish.** `fi-FI` is supported for speech to text.
- **Diarization.** Real-time diarization runs through `ConversationTranscriber`
  and returns `Guest-1`, `Guest-2`… Intermediate results get labels too
  when `DiarizeIntermediateResults` is on; otherwise they show
  `Speaker ID=Unknown`. No maximum speaker count is stated in the
  quickstart.
- **Code-switching.** Continuous language identification chooses among up
  to 10 candidate languages but "doesn't support changing languages within
  the same sentence". Microsoft has a separate page on configuring
  language identification together with diarization, which was not read
  [unverified that the two combine in real time].
- **Price.** The Azure Retail Prices API for West Europe gives "S1 Speech To
  Text" at $1.00/h and "Speech to Text Enhanced Feature Audio" at $0.30/h.
  The pricing page lists diarization as a real-time "enhanced add-on
  feature". That makes about **$1.30/h**, with 5 free hours per month.
- **Browser.** The JavaScript Speech SDK runs in browsers and takes an STS
  token "valid for 10 minutes" from `issueToken`, which the app must
  refresh.
- **Limits.** Maximum audio length for real-time diarization is 240 minutes
  per session.

### pyannoteAI Live-1 (diarization only) [verified]

- Launched July 2026. It does no transcription: it returns
  `diarization_speaker_start` and `diarization_speaker_end` events, each
  with a timestamp and a label (`SPEAKER_00`) that stays stable for the
  whole stream.
- It handles up to **8 speakers**, with more merged into one. Latency is
  "sub-300ms" [vendor].
- **Integration.** The same audio goes to the transcriber and to Live-1, and
  the two outputs are joined by timestamp. pyannote has a tutorial on
  pairing it with OpenAI realtime transcription.
- **Browser.** `POST /live` with the API key returns a **single-use
  WebSocket URL** that "you can hand … directly to your end-user's client".
- **Audio.** Raw **`pcm_f32le`, 16 kHz mono, in 100 ms chunks**, paced at
  real time (a buffer of more than 5 s closes the connection). This is a
  different format from most transcribers, so the browser would need to
  produce two encodings.
- **Price.** €0.198/h on the Developer (€19/month, credit included) and
  Starter plans. Billing is by audio seconds sent, with a 20 s minimum per
  stream. **Limit:** 5 hours per stream.

## Notes that apply to all of them

- **From final segment to utterance.** Most services label speakers per
  word or token (Speechmatics, Deepgram, xAI, Soniox, Azure), and their
  "final" is a stretch of text, not a single speaker's turn. Carl would
  have to split finals at speaker changes itself to make utterances.
  AssemblyAI's final `Turn` with `speaker_label` is closest to an utterance
  as delivered.
- **Late speaker corrections.** AssemblyAI (`SpeakerRevision`) and Soniox
  ("temporary speaker switches") both say that early speaker labels can be
  wrong. Carl acts on each utterance once, so it has to accept first-pass
  labels. A recording session can keep the revised labels for the test
  corpus.
- **Pause and silence cost money on some services.** AssemblyAI bills the
  whole session and Soniox bills streaming session time, so closing the
  stream during a **pause** saves cost as well as keeping the promise that
  Carl hears nothing. Deepgram and Soniox also close idle connections
  (10 s and 20 s) unless keepalives are sent.
- **Session caps against Carl's session.** A Carl session can run for hours
  and ends only on End, after 30 min with no utterance, or when the page
  closes. Google (5 min) and OpenAI (60 min) would force reconnects inside
  a normal dinner. Everyone else allows 3 h or more. Any reconnect restarts
  timestamps and speaker labels (`S1` in the new stream is not
  necessarily `S1` in the old one), which Carl's transcript handling has
  to allow for.
- **Recording sessions.** None of these services keeps the audio for Carl.
  A recording session would record locally in the browser (for example
  MediaRecorder) alongside the stream.

## Implications for Carl

These are observations, not decisions.

- **Provisional candidate 1: AssemblyAI Universal-3.6 Pro Streaming.** It is
  the only one with documented Finnish plus native fi/en code-switching,
  per-turn speaker labels, temporary browser tokens and a vendor-measured
  sub-second time to a final turn. Its cost is about $0.57/h, billed on
  session time.
- **Provisional candidate 2: Soniox stt-rt-v5.** It has the same language
  coverage at about a fifth of the price, with diarization included and
  browser-direct keys. Its own docs warn that endpointing lowers
  diarization accuracy, which is the trade-off Carl would sit on.
- **Provisional candidate 3: Speechmatics Enhanced with `fi`,** the
  established Finnish baseline with mature diarization, at $0.43/h. It
  would mangle English stretches unless Melia 1 Realtime ships with
  diarization (promised for Q4 2026). If it does, Speechmatics becomes a
  strong candidate again.
- **Fallback architecture.** pyannoteAI Live-1 plus any code-switching
  transcriber without diarization. Two streams and timestamp joining add
  complexity, so this is worth it only if the single-service candidates
  attribute speakers poorly on real table audio.
- **Next step.** Run the evaluation the earlier note recommended, on
  AssemblyAI, Soniox and Speechmatics rather than Grok and Chirp 3: a
  recorded 10–15 minute Finnish/English table conversation from a phone
  microphone, scored on word error rate per language, speaker-attribution
  accuracy, and the time from the end of speech to the final utterance.

## Sources

Speechmatics:

- https://docs.speechmatics.com/speech-to-text/realtime/quickstart
- https://docs.speechmatics.com/speech-to-text/languages.md
- https://docs.speechmatics.com/speech-to-text/models
- https://docs.speechmatics.com/private/melia-1-realtime.md
- https://docs.speechmatics.com/speech-to-text/realtime/realtime-diarization
- https://docs.speechmatics.com/speech-to-text/realtime/input.md
- https://docs.speechmatics.com/speech-to-text/realtime/limits
- https://docs.speechmatics.com/get-started/authentication
- https://www.speechmatics.com/pricing
- https://www.speechmatics.com/company/articles-and-news/introducing-melia-multilingual-speech-to-text-model
- https://github.com/speechmatics/speechmatics-python-sdk/pull/126

Deepgram:

- https://developers.deepgram.com/docs/models-languages-overview
- https://developers.deepgram.com/docs/multilingual-code-switching.md
- https://developers.deepgram.com/docs/diarization.md
- https://developers.deepgram.com/docs/understand-endpointing-interim-results.md
- https://developers.deepgram.com/docs/encoding.md
- https://developers.deepgram.com/docs/audio-keep-alive.md
- https://developers.deepgram.com/docs/recovering-from-connection-errors-and-timeouts-when-live-streaming-audio.md
- https://developers.deepgram.com/guides/fundamentals/token-based-authentication.md
- https://github.com/deepgram/deepgram-js-sdk (README, "Browser Usage")
- https://deepgram.com/pricing

Google:

- https://docs.cloud.google.com/speech-to-text/docs/models/chirp-3
- https://docs.cloud.google.com/speech-to-text/docs/quotas
- https://docs.cloud.google.com/speech-to-text/docs/release-notes
- https://cloud.google.com/speech-to-text/pricing

xAI:

- https://docs.x.ai/developers/model-capabilities/audio/speech-to-text.md
- https://docs.x.ai/developers/rest-api-reference/inference/voice.md
- https://docs.x.ai/developers/model-capabilities/audio/ephemeral-tokens.md
- https://x.ai/news/grok-voice-transcribe-2

AssemblyAI:

- https://www.assemblyai.com/docs/streaming/select-the-speech-model
- https://www.assemblyai.com/docs/streaming/multilingual-transcription
- https://www.assemblyai.com/docs/streaming/label-speakers-and-separate-channels
- https://www.assemblyai.com/docs/streaming/message-sequence
- https://www.assemblyai.com/docs/streaming/authenticate-with-a-temporary-token
- https://www.assemblyai.com/docs/streaming/common-session-errors-and-closures
- https://www.assemblyai.com/docs/streaming/benchmarks
- https://www.assemblyai.com/pricing

Soniox:

- https://soniox.com/docs/stt/models
- https://soniox.com/docs/stt/concepts/supported-languages
- https://soniox.com/docs/stt/concepts/language-hints
- https://soniox.com/docs/stt/concepts/speaker-diarization
- https://soniox.com/docs/stt/rt/real-time-transcription
- https://soniox.com/docs/stt/rt/endpoint-detection
- https://soniox.com/docs/stt/rt/limits-and-quotas
- https://soniox.com/docs/stt/rt/connection-keepalive
- https://soniox.com/docs/guides/temporary-api-keys
- https://soniox.com/docs/guides/direct-stream
- https://soniox.com/docs/api-reference/stt/websocket-api
- https://soniox.com/pricing

OpenAI:

- https://developers.openai.com/api/docs/guides/realtime-transcription
- https://developers.openai.com/api/docs/models/gpt-live-transcribe
- https://developers.openai.com/api/docs/guides/voice-webrtc
- https://developers.openai.com/api/docs/guides/realtime-conversations (60-minute session limit)

ElevenLabs:

- https://elevenlabs.io/docs/overview/capabilities/speech-to-text
- https://elevenlabs.io/docs/overview/models
- https://elevenlabs.io/docs/api-reference/speech-to-text/v-1-speech-to-text-realtime
- https://elevenlabs.io/docs/eleven-api/guides/how-to/speech-to-text/realtime/client-side-streaming
- https://elevenlabs.io/docs/eleven-api/guides/how-to/speech-to-text/realtime/transcripts-and-commit-strategies
- https://elevenlabs.io/pricing/api

Azure:

- https://learn.microsoft.com/en-us/azure/ai-services/speech-service/get-started-stt-diarization
- https://learn.microsoft.com/en-us/azure/ai-services/speech-service/language-support?tabs=stt
- https://learn.microsoft.com/en-us/azure/ai-services/speech-service/language-identification
- https://learn.microsoft.com/en-us/azure/ai-services/speech-service/speech-services-quotas-and-limits
- https://learn.microsoft.com/en-us/azure/ai-services/speech-service/rest-speech-to-text-short (STS token lifetime)
- https://azure.microsoft.com/en-us/pricing/details/speech/
- https://prices.azure.com/api/retail/prices (West Europe, product "Azure Speech")

pyannoteAI:

- https://www.pyannote.ai/blog/introducing-live-1-streaming-diarization
- https://docs.pyannote.ai/tutorials/streaming-real-time.md
- https://docs.pyannote.ai/administration/billing.md
- https://www.pyannote.ai/pricing
