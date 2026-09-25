# Resolve the spec's open issues

Type: grilling
Status: resolved
Blocked by: 07, 08, 09

## Question

Assembling [spec.md](../spec.md) left three contradictions the tickets didn't
resolve:

1. Does reaching the monthly cost cap end the session, or leave it open in the
   listening indicator's can't-check state ([07](07-success-criteria.md),
   [08](08-check-previous-carl-lessons.md), [09](09-session-lifecycle.md))?
2. Does the 6-month deletion of recording sessions also delete the test corpus
   built from them ([07](07-success-criteria.md), [09](09-session-lifecycle.md))?
3. Where does the owner's log of real sessions come from, when a normal session
   keeps only its fact cards ([07](07-success-criteria.md), [09](09-session-lifecycle.md))?

## Answer

Settled with the owner in a grilling session.

- **Monthly budget, warning only.** This overrides the cost cap in tickets 07,
  08 and 09.
  - The owner sets a **monthly budget**. The running-cost target stays at about
    €1 per hour of listening.
  - Exceeding it never stops anything: listening, checking and the session all
    carry on.
  - While the month is over budget, the listening indicator carries a
    prominent warning mark that everyone at the table sees. The Start screen
    shows the same warning before a session starts.
  - Being over budget is not a can't-hear-or-check state and is not a failure
    log stage.
- **The corpus outlives the audio.**
  - 6 months after recording, a recording session's audio, raw transcript and
    model-call logs are deleted.
  - Its owner-corrected Markdown stays in the test corpus until the owner
    deletes it. It keeps speaker labels (no names) and the location rounded to
    neighbourhood or town.
  - The decision, fact-checking and message-writing stages can be replayed on
    the whole corpus; speech-to-text only on the last 6 months of audio.
  - Anyone recorded may see the corrected Markdown or have it deleted at any
    time. It never goes into the repo.
  - The recording-session disclosure says the corrected text is kept beyond
    6 months.
- **The owner's log lives in the card archive.**
  - Each archived session also keeps its **listening time** (paused time
    excluded).
  - Between sessions, the owner can mark archived fact cards "wrong" or
    "pointless" and add a free-text note of missed moments. Still no
    transcript and no audio.
  - Anyone who was at the table may see or delete that session's cards, marks
    and notes.
  - The real-use wrong-card rate (per 10 h) is computed from these marks and
    listening times.

Glossary updated in `CONTEXT.md`: new term *Monthly budget*; *Listening
indicator*, *Failure log*, *Card archive*, *Recording session* and *Test
corpus* updated.
