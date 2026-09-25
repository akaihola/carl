# Streaming speech-to-text for Finnish and English table audio

Type: research
Status: resolved
Blocked by: 

## Question

Which streaming speech-to-text services (with speaker diarization) can transcribe Finnish and English table audio from a phone microphone in real time, well enough to build and record with? For each: Finnish support and code-switching, streaming diarization (how speaker labels arrive, how many speakers), final vs interim segments, latency to a final segment, price per hour of audio, whether a browser can connect directly (ephemeral tokens) or needs a server, audio format expected, session length limits and reconnects. Start from the candidates in [realtime-fact-checking.md](../../../docs/research/realtime-fact-checking.md). Findings go in `docs/research/streaming-speech-to-text.md`.

## Answer

Findings: [streaming-speech-to-text.md](../../../docs/research/streaming-speech-to-text.md)

- Only AssemblyAI Universal-3.6 Pro Streaming and Soniox stt-rt-v5 document Finnish, native Finnish/English code-switching and streaming diarization together.
- Speechmatics Enhanced and Deepgram Nova-3 support Finnish with streaming diarization, but only one language per stream. Speechmatics Melia 1 (which code-switches) is a Realtime preview with no speaker diarization until Q4 2026 and finals around 4 s.
- Four candidates drop out as documented: Google Chirp 3 (no streaming diarization, 5-minute streams), OpenAI gpt-live-transcribe (no speaker labels), ElevenLabs Scribe v2 Realtime (no realtime diarization parameter) and xAI Grok Voice Transcribe 2.0 (Finnish not in its 25 languages; docs say proxy the WebSocket).
- Price per hour with diarization: Soniox ≈ $0.12, xAI $0.20, Speechmatics $0.24–0.43, Deepgram ≈ $0.41, AssemblyAI ≈ $0.57, Azure ≈ $1.30. AssemblyAI and Soniox bill session time, so closing the stream during a pause saves money.
- All serious candidates let the browser connect directly with a short-lived token; Carl needs only a small token-minting endpoint, not an audio relay.
- Most services label speakers per word, so Carl must split finals at speaker changes to form utterances; AssemblyAI's final `Turn` with `speaker_label` is closest to an utterance as delivered.
- pyannoteAI Live-1 (€0.198/h, 8 speakers, browser-usable single-use URL) is a viable separate diarizer if single-service speaker attribution turns out poor.
- Provisional candidates to test on a recorded Finnish/English table conversation: AssemblyAI, Soniox, Speechmatics.
