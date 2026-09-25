# NVIDIA Parakeet v3 as Carl's speech-to-text

Research on whether NVIDIA's open **Parakeet v3** model
(`nvidia/parakeet-tdt-0.6b-v3`) could be Carl's speech-to-text and run
locally for free. Compiled 2026-09-25. It extends
[streaming-speech-to-text.md](streaming-speech-to-text.md), which covered
paid streaming services, and uses the vocabulary of
[CONTEXT.md](../../CONTEXT.md). An **utterance** is one final transcript
segment attributed to a single speaker. The question is how directly a
Parakeet setup can produce utterances with speaker labels, from a
2–6 person Finnish/English table, for sessions of up to 2 hours, fast enough
for a card to appear within seconds.

## How this was researched, and how far to trust it

- The claims come from NVIDIA's model cards on Hugging Face, the model's
  technical report, the documentation of NVIDIA's own local runtime
  (NeMo-Speech.cpp), the READMEs and file listings of the browser and ONNX
  ports, Chrome's WebGPU announcement, and Vast.ai's documentation and public
  offers API. All were read on 2026-09-25. Nothing was run on real audio or on
  a phone.
- **[verified]** means the claim was read on the cited primary page.
- **[vendor]** marks self-reported benchmark numbers. Model-card WERs are on
  read or broadcast speech (FLEURS), not on noisy conversation at a table.
- **[community]** marks a third-party port or a forum reply rather than NVIDIA
  documentation.
- **[estimate]** marks my own arithmetic or inference from the sources. These
  are the open questions to test.

## Summary

1. **Finnish is supported, and the accuracy on paper is reasonable.**
   Parakeet v3 covers 25 European languages including Finnish, with a FLEURS
   WER of 13.21% for Finnish and 4.85% for English [vendor]. It detects the
   language automatically.
2. **Finnish/English switching is weak.** NVIDIA staff say the model is
   "not fully tuned for codeswitching". A user reported that audio in half
   English and half Russian came out entirely as English [community]. It
   picks one language per chunk. A mixed Finnish/English table is the case it
   handles worst.
3. **It is not a streaming model.** NVIDIA's own runtime calls Parakeet TDT
   "offline-only". The runtime rejects live and streaming use for it and does
   not support streaming endpointing for it. The model card offers only
   *chunked* ("buffered") inference, with 2 s chunks plus 2 s of right
   context in its example. In practice Carl would cut the audio at pauses
   with a voice activity detector (VAD) and transcribe each piece as a whole.
   Since Carl acts only on final utterances, this suits it: a final could
   arrive roughly 1–2 s after someone stops talking on a GPU or a fast CPU
   [estimate].
4. **There is no diarization.** Speaker labels need a second model running
   over the whole stream, and Carl would join the two outputs by timestamp.
   The open options are NVIDIA's **Streaming Sortformer v2/v2.1** (at most 4
   speakers, "primarily trained on English") and the brand-new **Nemotron 3
   Diarization** (released 2026-09-23, up to 8 speakers, streaming at 0.32–1.04
   s latency, some multilingual training data). Both need a Linux machine with
   an NVIDIA GPU in NeMo, or NVIDIA's C++ runtime. **pyannote community-1**
   works only on whole recordings. **pyannoteAI Live-1** streams, but it is a
   paid service at €0.198/h.
5. **NVIDIA's own streaming sibling may fit Carl better.** **Nemotron 3.5
   ASR Streaming 0.6B** (June 2026) is a real streaming model with 80 ms to
   1.12 s chunks and 40 locales, including Finnish. NVIDIA's local runtime
   pairs it with Nemotron 3 Diarization in a single realtime WebSocket that
   tags words with speakers and sends a final per utterance. Its Finnish is
   weaker, though: 18.3–21.2% FLEURS WER against Parakeet v3's 13.2%
   [vendor].
6. **Where it could run:**
   - **In the phone's browser**, it is possible but not a good fit. There are
     community ports: parakeet.js (WebGPU and WASM) and sherpa-onnx (WASM).
     The model download is 0.4–2.5 GB, the ports publish no phone
     benchmarks, and there is no in-browser streaming diarizer.
   - **On the owner's own machine**, it is free and quick to try with
     NVIDIA's `nemo-speech serve`. It needs a tunnel to reach the phone, and
     an NVIDIA GPU to get diarization.
   - **On a rented Vast.ai GPU**, it costs about $0.06–0.54 per hour of
     session plus storage. That is no cheaper than Soniox's roughly $0.12/h
     once the setup and waiting for the GPU to start are counted.

## Parakeet v3 facts [verified]

| Property | Value |
| --- | --- |
| Model | `nvidia/parakeet-tdt-0.6b-v3`, 600M parameters, FastConformer encoder with a TDT decoder |
| Released | 2025-08-14 |
| Licence | CC-BY-4.0, so free commercial and private use with attribution |
| Languages | 25 European languages: bg, hr, cs, da, nl, **en**, et, **fi**, fr, de, el, hu, it, lv, lt, mt, pl, pt, ro, sk, sl, es, sv, ru, uk |
| Language choice | Automatic: it "automatically detects the language of the audio and transcribes it without requiring additional prompting". It takes no language prompt and outputs no language tag. |
| Output | Punctuation, capitalisation, word and segment timestamps |
| Long audio | Up to 24 min with full attention (on an A100 80 GB), or up to 3 h with local attention |
| Training data | About 670,000 h: 10,000 h human-transcribed (NeMo ASR Set 3.0) and 660,000 h pseudo-labelled (Granary) |
| Hardware listed | NVIDIA Ampere, Blackwell, Hopper, Volta; "at least 2GB RAM" |
| Local runtime | NVIDIA NeMo (Python), or NeMo-Speech.cpp with a `q8_0` GGUF |

### Finnish and English accuracy [vendor]

These are FLEURS WERs from the model card, using greedy decoding and no
language model:

| Language | Parakeet v3 (offline) | Nemotron 3.5 ASR Streaming, 1.12 s chunks, language given | Same, 80 ms chunks | Same, 1.12 s chunks, `auto` |
| --- | --- | --- | --- | --- |
| Finnish | **13.21%** | 18.34% | 21.19% | 18.72% |
| English | **4.85%** | 7.91% | 9.43% | 8.84% |

- Finnish is one of the weaker languages for Parakeet v3. Its FLEURS
  average is 11.97%, Spanish is 3.45% and German 5.04%. The card gives no MLS
  or CoVoST figure for Finnish.
- The technical report (arXiv 2509.14128) says Parakeet v3 is robust to
  noise: 12.21% WER at −5 dB SNR against 19.38% for Canary-1B-v2. That
  measurement is on English. The model card's own table reaches 19.88% at
  −5 dB.
- Table audio differs from FLEURS: people talk over each other, the phone
  sits far from the speakers, and there is cutlery noise. Expect higher WER
  in practice [estimate]. Only a recording session will show how much.

### Finnish/English switching

- On the model card's code-switching discussion, a user asked whether the
  model supports code-switching and reported that "the entire transcript was
  in English" for half-English, half-Russian audio. NVIDIA's reply
  (nithinraok, 2025-08-16): "Its not fully tuned for codeswitching
  capabilities." [community, NVIDIA staff]
- The model card's limitations section notes that accuracy varies with
  "Accent, Noise, Speech Type, Context of speech".
- Because segments come from a VAD, each utterance is transcribed on its
  own, so a switch *between* utterances gets its own language detection. A
  switch *within* a sentence ("se oli siis *the Battle of Hastings*") is where
  it is likely to go wrong [estimate]. The previous research found that
  AssemblyAI and Soniox document native within-sentence switching.

## Streaming and latency to a final segment

- **NVIDIA runtime.** The NeMo-Speech.cpp CLI guide says "Offline-only models
  such as Parakeet TDT reject `--stream` and `--live`." Its ASR configuration
  page adds that mid-stream endpointing (one final per utterance) "works with
  buffered CTC and cache-aware RNNT; the offline-only Parakeet TDT model does
  not support streaming endpointing" [verified].
- **NeMo Python.** The model card's "Streaming with Parakeet models" section
  points to NeMo's chunked-inference script
  (`speech_to_text_streaming_infer_rnnt.py`) with `chunk_secs=2`,
  `right_context_secs=2.0` and `left_context_secs=10.0` [verified]. With 2 s
  of right context, text cannot be final until about 2–4 s after it is
  spoken, before compute time [estimate].
- **VAD segmentation** is the practical pattern, and sherpa-onnx documents it
  for this model as "real-time/streaming speech recognition from a microphone
  with VAD" using Silero VAD [verified]. Silero VAD closes a segment after a
  set silence, for example 0.5–0.8 s (NeMo-Speech.cpp's endpointing default
  is 800 ms), and the whole segment is then transcribed. Time to a final is
  roughly the silence threshold plus the transcription time [estimate]:
  - On a GPU, the published RTFx is 3,332 on the Open ASR Leaderboard
    [vendor], so a 5 s segment takes milliseconds. **Final ≈ 0.6–1 s after
    speech ends.**
  - On a desktop CPU, sherpa-onnx reports RTF ≈ 0.325 for the int8 model
    [vendor], so a 5 s segment takes about 1.6 s. **Final ≈ 2–3 s.**
  - On a phone in the browser, nothing is published (see below).
- The weakness of VAD segmentation is long turns with no pause: a speaker
  who talks for 20 s produces no final until they stop. Carl would need a
  cap on segment length, such as cutting at 15 s. It is also exposed to
  overlapping speech, which one VAD stream cannot separate [estimate].
- **Nemotron 3.5 ASR Streaming** is the cache-aware alternative: chunks of
  80, 160, 320, 560 or 1,120 ms ("chunk size = current frame + right
  context"). In NeMo-Speech.cpp it supports endpointing, which sends one
  final per utterance after `stop_history_eou_ms` (default 800 ms) of
  trailing silence [verified]. It accepts `target_lang=auto`, which "detects
  the spoken language and emits the corresponding language code/tag" per
  utterance. The card does not mention switching within an utterance.

## Speaker diarization

Parakeet v3 does no diarization; its model card never mentions speakers.
Carl would have to run a diarizer over the same audio and give each
transcribed segment the speaker who holds most of its time span. NVIDIA's
Nemotron 3 Diarization blog does exactly this with Parakeet v3, assigning
words to speakers by their "midpoint" time [verified].

| Diarizer | Streaming | Speakers | Languages | Latency | Runs on | Licence / cost |
| --- | --- | --- | --- | --- | --- | --- |
| Streaming Sortformer 4spk v2 / v2.1 | Yes | **Max 4**; "performance degrades on recordings with 5 and more speakers" | "primarily trained on English… may degrade on non-English speech" | 0.32–30.4 s input buffer; RTF 0.093 at 1.04 s on an RTX 6000 Ada | NeMo on an NVIDIA GPU; NeMo-Speech.cpp | NVIDIA Open Model License; free |
| **Nemotron 3 Diarization** (2026-09-23) | Yes, plus offline | **Up to 8** | Trained on English plus multilingual sets (VoxConverse, DIHARD, CALLHOME, YODAS, a 21-language set); evaluated on multilingual DIHARD III and CALLHOME | 0.32, 0.64, 1.04 or 30.4 s input buffer | NeMo on Ampere, Hopper or Blackwell under Linux; NeMo-Speech.cpp | OpenMDW-1.1; free |
| pyannote community-1 | **No** (whole files) | Set by `min/max_speakers` | Any | – | CPU or GPU, Python | CC-BY-4.0, gated download; free |
| pyannoteAI Live-1 | Yes | Up to 8 | Any | "sub-300ms" [vendor] | Hosted; a browser can connect directly | €0.198/h plus a plan from €19/month, so **not free** |

- **Nemotron 3 Diarization accuracy** [vendor]:
  - DIHARD III: DER 9.69% for 1–4 speakers and 29.49% for 5–9 speakers at
    0.32 s latency.
  - For comparison, Sortformer v2.1 gets 14.37% and 42.71% on the same test.

  Diarization gets much worse above 4 speakers with either model, and a
  table of 5–6 is exactly that case.
- **Labels settle late.** NeMo-Speech.cpp warns that "speaker labels can
  change until the diarizer confirms them, which can take up to 10 s with
  V2". Carl acts on each utterance once, so it would either wait for the
  label to settle or accept the first label it gets. The earlier research
  found the same trade-off with AssemblyAI and Soniox.
- **Speakers are numbered in order of arrival** (the first voice heard is
  speaker 1). The numbering holds within one stream. After a reconnect it
  starts again from scratch.

## Where it could run

### 1. In the phone's browser (Android Chrome)

- **WebGPU on Android** has been on by default since Chrome 121 "on devices
  running Android 12 and greater powered by Qualcomm and ARM GPUs", rolled
  out gradually [verified].
- **parakeet.js** (MIT, community) runs `parakeet-tdt-0.6b-v3` with ONNX
  Runtime Web. Its WebGPU mode runs the encoder on WebGPU and the decoder in
  WASM. It caches the model in IndexedDB and has "stateful streaming
  helpers". Keet is its real-time demo app. Two caveats [verified]:
  - "In WebGPU modes, `int8` encoder requests are upgraded to `fp32`", and
    the fp32 encoder is **about 2.4 GB** (`encoder-model.onnx.data`,
    istupakov's export).
  - Multithreaded WASM needs COOP/COEP cross-origin isolation headers.
- **efederici's int4 export** is 409 MB in total. Its card says it works
  with "ONNX Runtime (CPU, WASM, WebGPU)", with RTF 0.086 on an unstated
  machine and about +0.4 pp WER on LibriSpeech [community]. It gives no
  Finnish figure after quantisation.
- **sherpa-onnx** has an int8 export (encoder 652 MB, about 640 MB in
  total). It documents VAD-based real-time use, an Android APK, WASM builds
  and Hugging Face Spaces [verified]. WASM runs on the CPU. Its WASM speaker
  diarization Space works on uploaded WAV files, not on a live stream.
- **transformers.js** lists "Parakeet" among its supported models. Whether
  that covers the TDT v3 checkpoint on WebGPU is [unverified].
- **What nobody publishes:** a real-time factor for Parakeet v3 on an
  Android phone, memory use in mobile Chrome, battery drain or heat over 2
  hours, or any streaming diarizer that runs in the browser. A 0.6B encoder
  running every few seconds for 2 hours on a propped-up phone is likely to
  hit thermal throttling [estimate].
- **Cost:** free. **Effort:** high. Carl would need a VAD, segment capping, a
  model download of 0.4–2.5 GB on first use, and fallbacks for devices
  without WebGPU. Speaker labels would still need Live-1, which is paid, or
  nothing. This conflicts with the requirement that Carl runs "on any
  device… just by browsing".

### 2. On the owner's own machine

- **NeMo-Speech.cpp** is "NVIDIA's official solution for local speech
  inference". It is a ggml-based C++ runtime with CPU, CUDA, Metal and
  Vulkan backends. It supports Parakeet TDT v3, Nemotron 3.5 ASR,
  Streaming Sortformer v2 and Nemotron 3 Diarization, "standalone or
  combined with ASR". `nemo-speech serve` provides [verified]:
  - a realtime WebSocket, `/v1/audio/transcriptions/realtime`, that takes
    PCM16 and sends `…delta` partials and `…completed` finals, with
    `speaker_diarization`, `word_timestamps` and `endpointing_ms` set per
    session;
  - an `?api_key=` query parameter for browser WebSockets, and a
    `--cors-origin` flag;
  - TLS only in a source build (`NEMO_SPEECH_HTTP_TLS=ON`);
  - a cap of 512 MiB of cumulative audio per realtime stream by default,
    which is about 4.6 h of 16 kHz PCM16 [estimate], enough for a 2 h
    session.

  NVIDIA calls NIM "the supported production deployment path; this server
  is intended for local use", which is fine for Carl.
- **The catch for Parakeet v3:** because TDT is offline-only, that realtime
  socket cannot produce a final per utterance with Parakeet. The combination
  that works out of the box is **Nemotron 3.5 ASR plus Nemotron 3
  Diarization**, at the Finnish accuracy shown above. Keeping Parakeet v3
  means custom code: a VAD cuts segments, each segment goes to Parakeet
  (for example through the HTTP transcription endpoint), a streaming
  diarizer runs over the continuous audio in parallel, and the two outputs
  are joined by time.
- **Hardware.** Parakeet v3 alone runs on a CPU (sherpa-onnx RTF ≈ 0.33). The
  NVIDIA diarizers list only NVIDIA GPUs for NeMo. NeMo-Speech.cpp's CPU,
  Metal and Vulkan backends may run them, but how fast is [unverified].
- **Reaching the phone.** The page is served over HTTPS, so it needs a
  `wss://` endpoint. That means a Cloudflare Tunnel or Tailscale Funnel, as
  in [hosting-small-backend.md](hosting-small-backend.md#a-home-machine-behind-a-tunnel-verified).
- **Cost:** free apart from electricity. **Effort:** medium. Installing and
  serving is a one-liner (`nemo-speech serve --asr-model … --diar-model …`).
  The tunnel and auth are an evening's work. Carl stops working whenever
  the machine or the home connection is down.

### 3. On a rented GPU (Vast.ai)

- **Prices.** Cheapest and median `dph_total` for verified, on-demand,
  single-GPU offers from Vast.ai's public offers API on 2026-09-25 [verified,
  live market, changes hourly]:

  | GPU | Offers | Cheapest $/h | Median $/h |
  | --- | --- | --- | --- |
  | RTX 3060 (12 GB) | 29 | 0.056 | 0.069 |
  | RTX A4000 (16 GB) | 11 | 0.083 | 0.110 |
  | RTX 3090 (24 GB) | 26 | 0.156 | 0.244 |
  | L4 (24 GB) | 6 | 0.269 | 0.322 |
  | RTX 4090 (24 GB) | 36 | 0.329 | 0.537 |
  | RTX 5090 (32 GB) | 48 | 0.450 | 0.709 |

  A 0.6B ASR model plus a diarizer should fit a 12 GB card [estimate]. The
  model cards give no minimum VRAM.
- **Billing** [verified]:
  - GPU time is billed per second while the instance runs.
  - **Storage is billed "even when instances are stopped"** until the
    instance is deleted.
  - Bandwidth is billed per byte, which is negligible at about 115 MB/h of
    PCM.
  - Interruptible instances are "50%+ cheaper" but "may be reclaimed", and
    losing the GPU mid-dinner would be unacceptable for Carl.
- **TLS.** Instances built on Vast base images get auto-generated Cloudflare
  tunnel URLs (`https://….trycloudflare.com`) per open port through the
  Instance Portal [verified]. That gives the phone a `wss://` address
  without setting up certificates. The URL changes with each instance
  [estimate].
- **Cost per session** [estimate]: about $0.07–0.55/h of GPU time while the
  instance runs, plus a few cents of storage per day it exists. A 2 h dinner
  on a 3060 costs about $0.15. That is similar to Soniox, about $0.12/h
  with diarization, Finnish and code-switching included.
- **Effort:** medium to high. The page would have to start an instance before
  each session and wait minutes for boot and model download (0.7–2.5 GB), or
  keep a stopped instance and pay storage. A stopped instance may not get its
  GPU back if another renter took it [unverified; the docs do not say].
  The Parakeet-specific glue from option 2 is also needed.

## What this means for Carl

- **Parakeet v3 is a credible free transcriber for a single-language
  session, and a poor one for a mixed Finnish/English table.** Its Finnish
  FLEURS WER (13.2%) is decent, but NVIDIA itself says it is not tuned for
  code-switching. It does not stream, and it has no diarizer of its own.
  None of the three hosting options gives Carl utterances with speaker
  labels without extra work.
- **If Carl goes self-hosted, try NVIDIA's streaming pair before Parakeet.**
  That pair is Nemotron 3.5 ASR Streaming with Nemotron 3 Diarization, served
  by `nemo-speech serve`. It gives finals per utterance with speaker tags
  over one browser-reachable WebSocket, with no glue code. The price is
  roughly 5 pp worse Finnish WER. Parakeet v3 could still be tried as a
  second pass on each segment when accuracy matters more than speed.
- **The phone's browser is the wrong place for it.** The model download is
  0.4–2.5 GB, there are no published phone benchmarks, and 2 hours of
  inference would drain the battery and heat the phone. It would also have
  no streaming diarizer. Keep the phone as a microphone and screen.
- **"Free" really means the owner's machine.** A Vast.ai GPU costs about
  the same as Soniox and adds starting the instance and managing storage.
  An owner machine with an NVIDIA GPU plus a tunnel is the only zero-cost
  path, and Carl then works only while that machine is up.
- **Suggested evaluation.** Add one local run to the recording-session test
  proposed in the earlier research, using the same 10–15 minute phone
  recording of a Finnish/English table. Run Nemotron 3.5 plus Nemotron 3
  Diarization, and Parakeet v3 on VAD segments, through NeMo-Speech.cpp.
  Score WER per language, speaker attribution with 4–6 speakers, and time
  from the end of speech to the final, against AssemblyAI and Soniox. The
  pluggable speech-to-text interface in AGENTS.md makes this swap cheap to
  keep open.

## Sources

NVIDIA models and paper:

- https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3 (model card; raw README read for tables and streaming section)
- https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3/discussions/1 (code-switching reply by NVIDIA staff)
- https://arxiv.org/abs/2509.14128 (Canary-1B-v2 & Parakeet-TDT-0.6B-v3 technical report)
- https://github.com/NVIDIA/NeMo/blob/main/examples/asr/asr_chunked_inference/rnnt/speech_to_text_streaming_infer_rnnt.py
- https://huggingface.co/nvidia/nemotron-3.5-asr-streaming-0.6b
- https://huggingface.co/nvidia/diar_streaming_sortformer_4spk-v2
- https://huggingface.co/nvidia/diar_streaming_sortformer_4spk-v2.1
- https://huggingface.co/nvidia/Nemotron-3-Diarization
- https://huggingface.co/blog/nvidia/nemotron-diarization

NVIDIA runtime (NeMo-Speech.cpp):

- https://github.com/NVIDIA/NeMo-Speech.cpp (README)
- https://github.com/NVIDIA/NeMo-Speech.cpp/blob/main/docs/server.md
- https://github.com/NVIDIA/NeMo-Speech.cpp/blob/main/docs/api.md
- https://github.com/NVIDIA/NeMo-Speech.cpp/blob/main/docs/cli.md
- https://github.com/NVIDIA/NeMo-Speech.cpp/blob/main/docs/asr/configuration.md

Browser and ONNX ports:

- https://github.com/ysdede/parakeet.js (README) and https://ysdede.github.io/keet/
- https://huggingface.co/istupakov/parakeet-tdt-0.6b-v3-onnx (file sizes via the Hugging Face API)
- https://huggingface.co/efederici/parakeet-tdt-0.6b-v3-onnx-int4
- https://huggingface.co/csukuangfj/sherpa-onnx-nemo-parakeet-tdt-0.6b-v3-int8
- https://k2-fsa.github.io/sherpa/onnx/pretrained_models/offline-transducer/nemo-transducer-models.html
- https://huggingface.co/spaces/k2-fsa/web-assembly-speaker-diarization-sherpa-onnx
- https://github.com/huggingface/transformers.js (README, supported models list)
- https://developer.chrome.com/blog/new-in-webgpu-121

Diarization (non-NVIDIA):

- https://huggingface.co/pyannote/speaker-diarization-community-1
- pyannoteAI Live-1: see the sources in [streaming-speech-to-text.md](streaming-speech-to-text.md)

Vast.ai:

- https://console.vast.ai/api/v0/bundles/ (public offers API, queried 2026-09-25 for verified on-demand single-GPU offers)
- https://docs.vast.ai/guides/instances/pricing
- https://docs.vast.ai/guides/reference/billing
- https://docs.vast.ai/documentation/instances/connect/instance-portal
