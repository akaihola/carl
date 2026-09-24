# Live conversation fact-checker – architecture research

Findings from the Claude chat "Real-time fact-checking for conversations",
compiled 2026-09-24. Vendor claims below are mostly self-reported; verify them
before relying on them.

## Goal

A mobile web app that listens to a two-person conversation at a table and
shows a short fact card when:

1. someone states something inaccurate or false, or
2. the conversation wonders about something without reaching the answer
   ("what was that actor's name…").

Core UX principle: **precision over recall.** One wrong "correction" destroys
trust. When unsure, show nothing.

## Pipeline

```
mic (browser) → streaming STT + diarization → detection (cheap, every utterance)
             → verification (expensive, only candidates) → push card to client
```

### 1. Audio capture (client)

- `getUserMedia` + AudioWorklet, 100–250 ms chunks, streamed over WebSocket.
- Ship as a PWA and use the Screen Wake Lock API.
- iOS Safari stops the microphone when the app is backgrounded.

### 2. Streaming speech-to-text with diarization

- Cloud streaming STT with two-speaker diarization.
- Only act on *final* segments, never interim ones.
- On-device Whisper via WebGPU is possible but slow and battery-heavy on phones.
- Language support (especially Finnish, if needed) varies a lot between
  vendors – test it.

### 3. Detection (cheap, fast, runs on every final utterance)

Input: the current utterance plus a short rolling context (the last few
utterances, not minutes of transcript).

Structured output:

- contains a checkable factual claim? (yes/no + confidence)
- is an open question / memory lapse? (yes/no + confidence)
- opinion / joke / hypothetical → ignore

Candidate models:

- **Claude Haiku** returning strict JSON.
- **TypeSafe AI "Jev"** – a strong fit for exactly this step (see below).

### 4. Verification (only for candidates, async queue)

- A stronger LLM with web search (e.g. Claude Sonnet + web search).
- Returns: verdict (`false` / `correct` / `uncertain`), a one-sentence
  correction or answer, source URL, and confidence.
- Only surface `false` claims and answered questions with high confidence.
  Never show `uncertain`.
- Send the whole utterance and its context to the verifier; the detector does
  not extract the claim text.

### 5. Delivery and UI

- Push cards back over the same WebSocket.
- Card: short title, one-sentence fact, source.
- Rate limit (e.g. at most one card per ~20 s), dedupe by topic, fade old cards.

### State and privacy

- Keep the per-session transcript and already-checked claims (e.g. in Redis)
  so nothing is checked twice.
- Tell the other person the conversation is being processed.
- Keep audio and text in memory only, with no persistent storage. Prefer
  GDPR-compliant vendors.

### Latency budget

| Stage        | Time      |
| ------------ | --------- |
| STT          | ~0.5–1 s  |
| Detection    | ~0.5 s    |
| Verification | 2–5 s     |

A card appears within a few seconds.

### Suggested stack

Next.js PWA · FastAPI or Node backend with WebSockets · streaming STT vendor ·
Haiku or Jev for detection · Sonnet + web search for verification · Redis for
session state.

## STT vendor landscape (summer–autumn 2026)

Baseline candidates: Speechmatics, Deepgram, AssemblyAI, Azure, Google Chirp 3.

New releases worth evaluating:

- **xAI Grok Voice Transcribe 2.0** (Sep 2026): batch and streaming, word
  timestamps, diarization at no extra cost, claimed ~2× more accurate than 1.0
  at the same price. The default model is still 1.0, so select
  `grok-voice-transcribe-2.0` explicitly. The most directly relevant new option.
- **pyannoteAI Live-1** (Jul 2026): streaming *diarization only*, no
  transcription. Useful for pairing the best STT with a separate diarizer.
- **Gladia Solaria-3** (Jun 2026): claims #1 accuracy on business and
  conversational audio for EN/FR/DE/ES/IT, but Gladia itself recommends it for
  post-meeting (async) use and Solaria-1 for real time. Not a direct fit.
- **AssemblyAI Universal-3.5 Pro** (Jul 2026): async flagship, not streaming.
- **Deepgram**: the newer v2 diarizer is batch-only; streaming uses v1.

No option is clearly superior for real-time two-person table audio.

**Recommended evaluation:** record 10–15 minutes of a real table conversation
on a phone microphone, run it through Grok Voice Transcribe 2.0, Speechmatics
and Google Chirp 3, and measure word error rate, speaker-attribution accuracy,
and latency to the first final segment.

## TypeSafe AI "Jev" for the detection step

- Released in limited early access on 2026-09-15. A "System One" model: it
  does not generate text but returns typed answers (Noul / Choice / Score
  primitives) with probabilities and confidence scores.
- Questions are evaluated in parallel and independently against one state, so
  adding questions barely affects latency. The vendor claims ~100× faster and
  cheaper than LLMs on such tasks (self-tested).
- Available via its own API, LangChain (`langchain-typesafe`,
  `TypeSafeClassifier`), Cloudflare Workers AI (`typesafe/jev`), and Vercel AI
  Gateway.
- **Fit:** ideal for step 3 – ask per utterance "contains a checkable factual
  claim?", "open question / memory lapse?", "opinion or joke?" and threshold
  on confidence.
- **Not a fit** for step 4: the vendor says it is weak at System 2 reasoning,
  specialized domains, and anything generative.
- **Caveats:** accuracy drops when the state contains unrelated content, so
  keep the context short and filter it in code. No published architecture or
  paper. Language support (e.g. Finnish) is undocumented.

**Recommended evaluation:** run Jev and Haiku side by side on the same
recorded transcript and compare hits against false alarms.

## Sources

- https://www.pyannote.ai/blog/introducing-live-1-streaming-diarization
- https://www.gladia.io/blog/solaria-3-speech-to-text-model-for-european-languages
- https://www.assemblyai.com/blog/top-speaker-diarization-libraries-and-apis
- https://releasebot.io/updates/xai (Grok Voice Transcribe 2.0)
- https://developers.deepgram.com/docs/diarization
- https://docs.cloud.google.com/speech-to-text/docs/release-notes
- https://typesafe.ai/blog/introducing-system-one-models-and-jev
- https://docs.typesafe.ai/introduction
- https://en.wikipedia.org/wiki/Jev_(AI_model)
- https://flaviocopes.com/jev/
- https://www.langchain.com/blog/building-a-harness-with-jev
- https://developers.cloudflare.com/ai/models/typesafe/jev/
