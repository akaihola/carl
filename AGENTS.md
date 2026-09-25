# Agent Instructions for Carl

## Goal

Carl is a live conversation fact-checker. It listens to a conversation at a
table and shows a short fact card when:

1. someone states something inaccurate or false, or
2. the conversation wonders about something without reaching the answer
   ("what was that actor's name…").

**Precision over recall.** One wrong "correction" destroys trust. When unsure,
show nothing.

## Requirements

- **Runs on any device with a microphone and a display** just by browsing to
  Carl's web page. No app install and no platform-specific code.
- **Visual output only.** Cards are shown on screen; there is no
  text-to-speech.
- **Pluggable models.** Each stage sits behind a small, provider-neutral
  interface so implementations can be swapped through configuration without
  touching the rest of the pipeline:
  - **Speech-to-text** – streaming transcription with speaker diarization.
  - **Decision model** – cheap and fast; runs on every final utterance and
    decides whether it holds a checkable claim or an unanswered question.
  - **Fact-checking model** – stronger and slower; runs only on candidates and
    returns a verdict, answer, source and confidence.
  - **Message-writing model** – turns a confident verdict into the short card
    shown to the user.

## Pipeline

```
mic → speech-to-text → decision → fact-checking → message writing → card on screen
```

Act only on final transcript segments, keep the context passed to the decision
model short, and never surface uncertain verdicts.

## Research

See [docs/research/realtime-fact-checking.md](docs/research/realtime-fact-checking.md)
for the architecture research, vendor landscape and candidate models.
