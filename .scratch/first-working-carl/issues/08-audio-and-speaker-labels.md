# How audio is streamed and how speaker labels reach the decision model

Type: grilling
Status: claimed
Blocked by: 06, 07

## Question

How does audio get from the microphone to speech-to-text (format, chunking, transport, reconnects, Pause), and how do final segments with diarization become utterances with speaker labels for the decision model (segment merging, label stability over a 2 h session, overlapping speech)?

## Comments

- From [Provisional models for each stage](07-provisional-models.md#answer): speech-to-text is Soniox stt-rt-v5 behind a server-side adapter that emits interim and final events with per-word speaker labels; the pipeline splits finals into utterances.
