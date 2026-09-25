# Carl: product spec

Assembled from the resolved tickets of the [Purpose and goal map](map.md).
Terms in **bold** are defined in [`CONTEXT.md`](../../CONTEXT.md). Where two
tickets differ, the later one wins; each section links the tickets it comes
from, and the rationale lives there.

## What Carl is for

Carl is a live conversation fact-checker. It overhears a conversation at a
**table** and shows a short **fact card** on screen in two cases only:

1. someone states a **claim** that is false, or
2. the table wonders about an **open question** and leaves it unresolved
   ("what was that actor's name…", "was it 1953 or '54?").

**Precision over recall.** One wrong card destroys trust. When unsure, Carl
shows nothing.

Carl is an experiment for private, personal use, not a product. That limit is
deliberate.

Sources: [04](issues/04-edges-of-purpose.md), [map Notes](map.md#notes).

## Who uses it

- The **owner** runs Carl on their own phone and discloses it to the table.
- The **table** is the owner plus 1–5 adults they know well. Children may be
  present but are not a design target.
- 2–6 speakers, usually 3–4; more than 6 is best-effort. Carl tells speakers
  apart but does not identify them.

Sources: [03](issues/03-situations.md), [05](issues/05-social-contract.md).

## Situations it serves

- **Built for:** dinner or coffee at home. Restaurants, cafés and informal work
  lunches are supported but not optimised for.
- **Device:** the owner's phone, propped up so the whole table can see it,
  opened as a web page. Its built-in microphone, 0.5–2 m from the speakers,
  with normal household noise.
- **Language:** Finnish and English, both fully. The language may switch
  between **utterances**, and Finnish speech carries English loanwords. Fact
  cards are written in the conversation's main language.
- **Length:** a **session** runs 30 min to 2 h in the background.

Sources: [03](issues/03-situations.md).

## What Carl deliberately doesn't do

**Non-goals**

- No fact card other than the two triggers: no definitions, pertinent numbers,
  "did you know" asides or chit-chat. Carl never confirms a true claim unless
  the table disagrees about it, which makes it an open question.
  ([04](issues/04-edges-of-purpose.md))
- No speech output. Cards are visual only. ([08](issues/08-check-previous-carl-lessons.md), `AGENTS.md`)
- No wake word and no direct questions to Carl; it only overhears.
  ([04](issues/04-edges-of-purpose.md))
- No judgement of opinions, predictions, private or personal facts, or
  contested questions with no settled answer. On contested topics Carl stays
  silent rather than taking a side. ([04](issues/04-edges-of-purpose.md))
- No refusal by category: named people, quotes and unresolved pronouns are
  judged like anything else, with confidence carried in the wording.
  ([04](issues/04-edges-of-purpose.md), [map Notes](map.md#notes))
- No owner-only or hidden mode. ([05](issues/05-social-contract.md))
- No speaker names or "you" on a card. ([05](issues/05-social-contract.md))

**Out of scope for Carl**

- Video calls, cars, wearables, second screens, several combined devices,
  languages other than Finnish and English. ([03](issues/03-situations.md))
- Any install, app or platform-specific code. (`AGENTS.md`)

**Out of scope for this spec** ([map](map.md#out-of-scope))

- Choosing vendors and models for each stage, and how confidence is measured.
- Implementation architecture.
- Public-product concerns: onboarding, billing, multi-tenant accounts.
- Research on how people react to being corrected by a machine.

## How Carl behaves

### Triggers

- A **claim** is checkable as true or false against a public source, given
  where and when the table is. A misremembered quote ("as Churchill said…") is
  a false claim.
- An **open question** is something a public source can answer, given where
  and when the table is, that the table leaves unresolved. A disagreement the
  table can't settle is an open question.
- Situational questions count when a public source can answer them ("when was
  this church built?", "is the pharmacy on the corner open on Sundays?").
  Private facts ("how old is my sister?") and opinions ("what should we
  order?") don't.
- The **decision model** acts only on final utterances.

Sources: [04](issues/04-edges-of-purpose.md), [08](issues/08-check-previous-carl-lessons.md).

### Pedantry threshold

A false claim earns a card only when the error changes the point being made, or
when it repeats a well-known myth ("Einstein failed maths"). Loose
approximations, off-by-one details that don't matter to the point, and claims
true under a reasonable reading get nothing.

Source: [04](issues/04-edges-of-purpose.md).

### Confidence bands

Same bands for both triggers:

| **Verdict** | Shown |
| --- | --- |
| Confident, with a citable source | Plain fact card |
| Likely, with a citable source | **Hedged fact card** ("probably", "maybe"), also marked visually |
| Anything lower, or no citable source | Nothing |

Never surface unsourced or low-confidence verdicts; hedge moderate ones.

Sources: [04](issues/04-edges-of-purpose.md), [06](issues/06-fact-card-behaviour.md).

### The table comes first

- No grace period: a card shows as soon as it is ready, for both triggers.
- If the table corrects the claim or answers the open question before the card
  is ready, Carl drops it.
- If the table settles it while the card is on screen, the card stays, marked
  "Settled at the table" / "Ratkesi pöydässä".
- A "correction" from the table that is itself false is a new claim.
- One card per claim or open question per session. A repeat gets nothing new;
  the earlier card stays in the **card history**.

Sources: [04](issues/04-edges-of-purpose.md), [06](issues/06-fact-card-behaviour.md), [08](issues/08-check-previous-carl-lessons.md).

### The fact card

- A title, a one-sentence fact and a source. It gives the claim's gist in a few
  words, then the fact ("Einstein didn't fail maths: he excelled at it.").
- A coloured label tells claims from open questions (Claim / Väite,
  Question / Kysymys). Hedged fact cards are marked visually as well as in
  their wording.
- Readable across the table from 0.5–2 m, and stands alone without the
  conversation around it.
- Neutral reference-book voice, the encyclopedic register in Finnish. No
  "Actually", exclamation marks, jokes or emoji. In a hedged card only
  "probably"/"maybe" carries the uncertainty.

Sources: [05](issues/05-social-contract.md), [06](issues/06-fact-card-behaviour.md).

### The screen

- Only fact cards and the **listening indicator** (with the one-tap **Pause**
  and End) reach the screen. A failed check is silent.
- One large card at a time. It stays until someone taps it away. When another
  card is waiting, the current one gives way on a timer or a tap. Cards never
  stack.
- Earlier cards collect in the **card history**, newest on top, older ones
  smaller and dimmer, out of the way of the current card.
- A **late card** (ready more than 20 s after its utterance) skips the screen
  and goes straight into the card history at its place by utterance time, with
  no special mark.
- The listening indicator is always visible and shows one of: listening,
  recording (in a **recording session**), paused, or can't hear or check
  (connection lost, a stage down, cost cap reached).
- An optional **live transcript line** next to the indicator shows the latest
  utterance; it can be switched on and off. Between cards, the indicator (and
  this line, if on) is all that is on screen, which is how Carl shows it is
  listening while it has nothing to say.
- The screen stays on for the whole session. The documentation tells the owner
  that a long session wants a charger.

Sources: [05](issues/05-social-contract.md), [06](issues/06-fact-card-behaviour.md), [07](issues/07-success-criteria.md), [08](issues/08-check-previous-carl-lessons.md).

### Social contract

- Everyone at the table sees every card at the same moment.
- The owner tells the table that Carl is listening. Anyone's objection means
  Carl doesn't run. Carl makes no announcement of its own.
- **Suggested disclosure line** (given to the owner): the conversation, and the
  phone's location unless switched off, go to cloud AI services.
- Anyone can **Pause** with one tap. While paused, nothing is heard or kept,
  and only another tap resumes.
- A card addresses the claim, never the person.

Sources: [05](issues/05-social-contract.md), [08](issues/08-check-previous-carl-lessons.md), [09](issues/09-session-lifecycle.md).

### Session lifecycle

- **Start:** the owner taps Start after telling the table. Nothing is heard
  before that tap.
- **End:** anyone taps End; or 30 min pass without an utterance, paused or
  not; or the page is closed. There is no hard time limit. The monthly cost
  cap also stops Carl (see [Open issues](#open-issues)).

Source: [09](issues/09-session-lifecycle.md).

### What Carl keeps

**A normal session**

- Keeps only its fact cards. At the end, the card history moves into the
  **card archive** (title, fact, source, time, grouped by session), kept on the
  owner's phone until the owner deletes it.
- The archive can be opened only when no session is running.
- The transcript and live transcript line are discarded when the session ends.
  No audio is kept. The archive doesn't keep the location.
- Anyone who was at the table may ask to see a session's cards or have them
  deleted, and the owner honours it.
- The **failure log** records moments Carl couldn't hear or check: time, stage
  (speech-to-text, decision, fact-checking, message writing, connection, cost
  cap) and error, with no conversation content. It opens from a "Log" menu at
  any time, entries expire after 30 days, and the owner can clear it.

**A recording session** (development mode)

- Visibly marked on the listening indicator and disclosed on its own. Anyone's
  objection means the session runs without recording. Pause stops recording.
- Keeps its fact cards, the full transcript, the audio and the full log of
  every model call (including the location). Raw logs are not deleted after
  correction.
- Deleted automatically 6 months after it was recorded.
- Heard or read only by the owner and by the models Carl is tested with; never
  put in the repo.
- Anyone recorded may ask to hear or read it, or to have it deleted. Deletion
  removes the whole session. The owner honours a request without asking why.

**Model providers:** no limit on what each stage's provider keeps or trains
on. Carl's documentation names each stage's provider and links to its
retention terms.

Sources: [07](issues/07-success-criteria.md), [08](issues/08-check-previous-carl-lessons.md), [09](issues/09-session-lifecycle.md).

### Failures

- A failed check shows nothing; there is no error text on screen.
- When Carl can't hear or can't check at all, the listening indicator shows
  that state instead of claiming to listen, and the failure log records it.
- At the monthly cost cap, Carl stops cleanly.

Sources: [07](issues/07-success-criteria.md), [08](issues/08-check-previous-carl-lessons.md).

### Context Carl gets

- A short recent transcript, passed to the decision model; utterances carry
  speaker labels (speakers told apart, not named).
- The date, time and the phone's precise location, taken at session start and
  updated during it. The owner can switch location off; Carl then gets only
  the date and time.

Sources: [03](issues/03-situations.md), [08](issues/08-check-previous-carl-lessons.md), `AGENTS.md`.

## How we'd know it works

**Measured on** a **test corpus** built from recording sessions, and on the
owner's log of real sessions (wrong or pointless cards, moments Carl should
have spoken). The corpus is the gate before Carl runs at a real table.

- Each recording session becomes one Markdown file: the full cleaned
  transcript (speaker label, timestamp, small talk included), each
  **candidate** with a summary of its verdict, the card text and the **check
  time**.
- The owner marks each card **deserved** or **not deserved** with a reason
  (wrong, nitpick, opinion, contested, already settled, not checkable), adds
  missed candidates, and fixes transcript errors.
- The corpus keeps the corrected Markdown and the audio, so the whole pipeline
  can be replayed.

**Targets**

| Measure | Target |
| --- | --- |
| Precision (test corpus) | ≥ 95% of fact cards deserved, hedged cards included |
| Wrong plain cards (test corpus) | none |
| Wrong cards (real use) | at most about 1 per 10 h of conversation |
| Recall floor (test corpus) | ≥ 1 in 3 claims, ≥ 1 in 5 open questions get a card |
| Check time | median ≤ 4 s, 90th percentile ≤ 8 s |
| Running cost | about €1 per hour of listening, all stages; monthly cap set by the owner |

- The same precision bar for both triggers. A trigger's figure is provisional
  until it has at least 30 scored cards with both Finnish and English
  represented.
- No cards-per-session floor: some dinners hold nothing worth a card.
- Late cards still count towards precision. A card on screen before the table
  settles the point is fine.

Source: [07](issues/07-success-criteria.md), amended by [09](issues/09-session-lifecycle.md).

## Open issues

Contradictions or gaps the tickets don't resolve:

1. **Cost cap: end the session, or keep it open?** [07](issues/07-success-criteria.md)
   says Carl "stops cleanly" at the monthly cap and [09](issues/09-session-lifecycle.md)
   says the cap "still stops Carl", but [08](issues/08-check-previous-carl-lessons.md)
   lists "cost cap reached" as a state of the listening indicator during a
   session. Does reaching the cap end the session (card history to the
   archive), or leave it running in the can't-check state until End or the
   30-min timeout?
2. **Does the 6-month deletion shrink the test corpus?** [09](issues/09-session-lifecycle.md)
   deletes each recording session 6 months after recording, while the test
   corpus ([07](issues/07-success-criteria.md)) is the owner-corrected Markdown
   and audio from those sessions and is meant for later vendor comparisons.
   Is the corrected Markdown and audio deleted with the session, so the corpus
   is a rolling 6-month window (and the 30-scored-cards threshold can lapse),
   or does the corpus outlive the raw session?
3. **Where the owner's log of real sessions comes from.** [07](issues/07-success-criteria.md)
   measures real use from the owner's log of wrong cards and missed moments,
   and a wrong-card rate per 10 h of conversation. A normal session keeps only
   its cards ([09](issues/09-session-lifecycle.md)): no transcript and no
   recorded session length. Is this log the owner's own notes outside Carl, or
   should the card archive also keep session duration and a way to mark cards?
