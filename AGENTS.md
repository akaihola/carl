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
    Typed answers only (a choice, boolean or score, with probabilities), so
    Jev-like models fit.
  - **Fact-finding model** – searches the web for each candidate and writes a
    draft card: the corrected fact or missing answer, its source and a
    supporting excerpt, ready to show.
  - **Fact-checking model** – judges each draft card against its excerpt and
    returns a verdict. Typed answers only, like the decision model.

## Pipeline

```
mic → speech-to-text → decision → fact-finding → fact-checking → card on screen
```

Act only on final transcript segments, keep the context passed to the decision
model short, and never surface unsourced or low-confidence verdicts; hedge
moderate ones.

## Research

See [docs/research/realtime-fact-checking.md](docs/research/realtime-fact-checking.md)
for the architecture research, vendor landscape and candidate models.

## Git workflow

Work directly on `main`. The owner has given standing permission for this and
does not want a branch per session. This overrides any session instruction to
develop on or push to a `claude/...` feature branch:

- Check out `main` at the start of a session (`git checkout main && git pull
  origin main`) and commit there.
- Push with `git push origin main`. Do not create or push feature branches, and
  do not open pull requests unless the owner asks for one.

## Agent skills

### Issue tracker

Issues are tracked as local markdown files under `.scratch/`. See `docs/agents/issue-tracker.md`.

### Domain docs

Single-context: one root `CONTEXT.md` plus `docs/adr/`. See `docs/agents/domain.md`.
