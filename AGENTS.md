# Agent Instructions for Carl

## Goal

Carl is a live conversation fact-checker for private, personal use: an
experiment, not a product. The owner props their phone up at a table of 2–6
people they know well (dinner or coffee at home, Finnish and English), and Carl
overhears the conversation and shows everyone a short fact card only when:

1. someone states a claim that is false, checkable against a public source,
   and wrong enough to change the point (or a well-known myth), or
2. the table wonders about an open question a public source can answer and
   leaves it unresolved ("what was that actor's name…").

Nothing else: no asides, no confirmations, no speech, no wake word.

**Precision over recall.** One wrong "correction" destroys trust. Never surface
unsourced or low-confidence verdicts; hedge moderate ones ("probably",
"maybe"). When unsure, show nothing.

The full product spec, including success criteria, is
[.scratch/purpose-and-goal/spec.md](.scratch/purpose-and-goal/spec.md).

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
  - **Message-writing model** – turns a confident verdict into a plain fact
    card, or a likely one into a hedged fact card, shown to the whole table.

## Pipeline

```
mic → speech-to-text → decision → fact-checking → message writing → card on screen
```

Act only on final transcript segments, keep the context passed to the decision
model short, and never surface unsourced or low-confidence verdicts; hedge
moderate ones.

## Research

See [docs/research/realtime-fact-checking.md](docs/research/realtime-fact-checking.md)
for the architecture research, vendor landscape and candidate models.

## Agent skills

### Issue tracker

Issues are tracked as local markdown files under `.scratch/`. See `docs/agents/issue-tracker.md`.

### Domain docs

Single-context: one root `CONTEXT.md` plus `docs/adr/`. See `docs/agents/domain.md`.
