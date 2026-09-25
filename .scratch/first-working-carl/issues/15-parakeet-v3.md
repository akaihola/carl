# Running Parakeet v3 for Carl's speech-to-text

Type: research
Status: resolved
Blocked by: 

## Question

Could NVIDIA's Parakeet v3 models (e.g. parakeet-tdt-0.6b-v3) serve as Carl's speech-to-text, run locally for free? Check: Finnish support and accuracy, Finnish/English switching, streaming or chunked real-time use and latency to a final segment, speaker diarization (none built in? pairing with Sortformer, pyannote or pyannoteAI Live-1), and where it could run: in the phone's browser (WebGPU/WASM ports such as transformers.js or sherpa-onnx, on Android Chrome), on the owner's own machine, or on a rented GPU (Vast.ai is the owner's choice), with rough cost and effort for each. Findings go in `docs/research/parakeet-v3.md`.

## Answer

Researched 2026-09-25; findings in [parakeet-v3.md](../../../docs/research/parakeet-v3.md).
Nothing was tested on real audio or a phone.

- **Parakeet v3 alone isn't suitable.** Finnish is supported (13.2% FLEURS
  WER, NVIDIA's figure), but NVIDIA staff say it is "not fully tuned for
  codeswitching". NeMo-Speech.cpp treats it as offline-only, so Carl would
  have to cut audio at pauses with a voice activity detector (estimated
  0.6–1 s to a final on a GPU, 2–3 s on a desktop CPU) and add a separate
  diarizer.
- **Diarizers:** Streaming Sortformer is capped at 4 speakers and trained
  mainly on English, and the error rate roughly triples above 4 speakers;
  pyannote community-1 is offline only; pyannoteAI Live-1 streams but costs
  €0.198/h.
- **Self-hosted option to test first:** Nemotron 3.5 ASR Streaming +
  Nemotron 3 Diarization (released 2026-09-23, up to 8 speakers), served by
  NVIDIA's runtime as one realtime WebSocket with per-utterance finals and
  speaker tags; weaker Finnish (18–21% WER).
- **Where it could run:** in the phone's browser, not viable (0.4–2.5 GB
  download, no phone benchmarks, no in-browser streaming diarizer). On the
  owner's machine with an NVIDIA GPU and a tunnel, free and medium effort.
  On Vast.ai, ~$0.06–0.54/h plus storage billed while stopped, no cheaper
  than Soniox at ~$0.12/h.
- **Suggestion:** add a local run of both NVIDIA setups to the planned
  comparison against AssemblyAI and Soniox on recording sessions.
