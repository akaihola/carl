# How audio is streamed and how speaker labels reach the decision model

Type: grilling
Status: resolved
Blocked by: 06, 07

## Question

How does audio get from the microphone to speech-to-text (format, chunking, transport, reconnects, Pause), and how do final segments with diarization become utterances with speaker labels for the decision model (segment merging, label stability over a 2 h session, overlapping speech)?

## Comments

- From [Provisional models for each stage](07-provisional-models.md#answer): speech-to-text is Soniox stt-rt-v5 behind a server-side adapter that emits interim and final events with per-word speaker labels; the pipeline splits finals into utterances.

## Answer

Settled with the owner in a grilling session (2026-09-26).

**Audio from the microphone to the server**

1. **Format:** raw 16 kHz 16-bit mono PCM from an AudioWorklet
   (`AudioContext({sampleRate: 16000})`), in chunks of about 100 ms (~115 MB/h,
   fine on home wifi). Each chunk stands alone, so reconnects and Pause need no
   container headers; the server passes the bytes to Soniox unchanged (`s16le`).
   How recordings are compressed for storage is left to
   [Where the card archive, failure log and recording sessions are kept](11-storage-expiry-deletion.md).
2. **Transport:** one WebSocket between page and server. Binary frames carry
   audio; JSON text frames carry Start, Pause, End, the heartbeat, cards and
   the listening-indicator state.
3. **Microphone processing:** `echoCancellation` and `noiseSuppression` off,
   `autoGainControl` on. The page reads back `track.getSettings()` and each
   recording session stores it. The comparison map may revisit this.

**Speech-to-text stream**

4. **Segment ends:** Soniox endpoint detection on, with
   `max_endpoint_delay_ms` in the config file, starting at 1,500 ms;
   `language_hints: [fi, en]`. The comparison map can test endpointing off
   (better speaker attribution, Carl's own silence timer) on the recordings.
5. **Page drops:** during the 2-minute reconnect grace period the server keeps
   the Soniox stream open with keepalives (at most ~$0.004), so speaker labels
   carry on after a short drop.
6. **Soniox drops:** the server reopens at once as a new stream, backing off
   1, 2, 4… up to 30 s; meanwhile the listening indicator shows "can't hear or
   check" and the failure log records the gap. A stream nearing Soniox's
   300-minute cap is rotated at the next segment end.
7. **Pause:** the server sends Soniox's manual finalise, so words spoken
   before the tap become final and are processed normally, then closes the
   stream (as already decided in
   [What runs in the browser and what runs on a server](06-browser-and-server-split.md#answer)).
   Pause acts from the tap forward.

**From final segments to utterances**

8. **Splitting:** a segment is split wherever the speaker label changes. A run
   of 2 words or fewer between two runs of the same speaker is treated as a
   false switch and merged into them. An utterance longer than about 30 s is
   split at the next sentence end, so the decision model never waits on a
   monologue. The recording keeps Soniox's raw tokens and labels, so
   corrections and replays see what speech-to-text actually said.
9. **Overlapping speech:** no special handling; the loss is accepted and the
   recorded audio lets the comparison map measure it.
10. **Speaker labels are scoped to their stream.** Soniox numbers speakers
    per stream, so every new stream (after Pause, a Soniox drop, a server
    restart or rotation) gets fresh labels (e.g. B1, B2…), and the decision
    context gets a "(paused)" or "(gap)" marker at the boundary. No voice
    matching across streams. **Speaker label** is now in `CONTEXT.md`.

No ADR: each choice is cheap to reverse through config or a small change,
and the comparison map exists to revisit them.
