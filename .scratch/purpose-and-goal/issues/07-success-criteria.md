# Success criteria

Type: grilling
Status: resolved
Blocked by: 04

## Question

What does "Carl works" mean for this experiment: a precision target (and any recall floor), how it is measured (e.g. a corpus of recorded table conversations with labelled candidates), and the tolerances for latency and running cost?

## Context from resolved tickets

- From [Edges of the purpose](04-edges-of-purpose.md): precision is judged against a threshold. Only errors that change the point, or that repeat a well-known myth, deserve a card, and hedged cards count as cards. Labelled data has to encode this: a nitpick card is a false positive, as is a card on an opinion, a contested topic, or a candidate the table already resolved.
- From [Fact card behaviour](06-fact-card-behaviour.md): the check time (end of utterance to card on screen) was left for this ticket. In the prototype, a 3 s check put a card up before the table corrected the claim itself, which then shows as "Settled at the table". With 8 s the table got there first and the card was dropped. The latency tolerance should weigh a card arriving too late against one arriving before the table has had its say.

## Answer

Settled with the owner in a grilling session.

- **How "works" is judged: both a test corpus and real sessions.** The test corpus is the gate before Carl runs at a real table. The owner's log of real sessions (wrong or pointless cards, moments Carl should have spoken) shows whether it holds up.
- **The test corpus comes from recording sessions.** A dev version of Carl records the audio, transcripts and its own model logs. It then cleans them up and summarises them into one Markdown file per recording session, which the owner corrects:
  - the full cleaned transcript (utterances with speaker label and timestamp), small talk included, because missed candidates hide in it;
  - each flagged candidate, with a summary of its verdict, the card text and the check time;
  - the owner's corrections: each card marked **deserved** or **not deserved**, with a reason (wrong, nitpick, opinion, contested, already settled, not checkable); **missed** candidates added where they occurred; transcript errors fixed.
  - "Summarised" applies to the model logs, not the conversation.
- **What the test corpus keeps:** the corrected Markdown plus the audio, so later vendor comparisons can replay the whole pipeline, speech-to-text and speaker separation included. Raw logs are deleted once the Markdown is corrected.
- **Recording is a separate, visibly marked mode.**
  - The listening indicator shows that Carl is recording, not just listening.
  - The owner discloses the recording explicitly. Anyone's objection means the session runs without recording.
  - Pause stops recording as well.
  - What happens to recordings afterwards is left to [Session lifecycle and what Carl keeps](09-session-lifecycle.md).
- **Precision:**
  - At least **95%** of fact cards deserve to be shown. Hedged cards count.
  - **No factually wrong plain card** in the test corpus.
  - In real use, at most about **one wrong card per 10 hours** of conversation.
  - The same bar for both triggers.
  - A trigger's figure counts once it has at least **30 scored cards** with both Finnish and English represented. Until then it is provisional.
- **Recall floor, on the test corpus:**
  - At least **1 in 3** labelled claims and **1 in 5** labelled open questions get a card.
  - No cards-per-session floor, since some dinners hold nothing worth a card. The listening indicator and the live transcript line answer the "silent Carl looks broken" problem.
- **Check time** (end of utterance to card on screen):
  - Target: **median ≤ 4 s**, **90th percentile ≤ 8 s**.
  - A **late card** (ready more than **20 s** after its utterance) is not shown in the spotlight. It goes into the card history at its place by utterance time, so it can be scrolled back to, with no special mark or signal. It still counts towards precision.
  - A card on screen before the table settles the point is fine: it gets marked "Settled at the table" as already decided.
- **Running cost:**
  - About **€1 per hour** of listening at most, all stages included.
  - A **monthly cap** set by the owner. Carl stops cleanly when it is reached.
  - Fitting vendors to this stays with the vendor effort (out of scope).

Glossary updated in `CONTEXT.md`: *Check time*, *Late card*, *Recording session*, *Test corpus*.

## Comments

- Superseded in part by [Session lifecycle and what Carl keeps](09-session-lifecycle.md): recording sessions keep the raw model-call logs too, and each is deleted 6 months after it was recorded.
- Superseded in part by [Resolve the spec's open issues](10-spec-open-issues.md): the monthly cap becomes a **monthly budget** that only warns and never stops Carl; the corrected Markdown stays in the test corpus after the 6-month deletion (audio does not); the owner's log of real sessions lives in the card archive (listening time, cards marked wrong or pointless, notes).
