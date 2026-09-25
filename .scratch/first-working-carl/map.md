# Map: First working Carl

Label: wayfinder:map

## Destination

A decided plan for the first working version of Carl at
`.scratch/first-working-carl/spec.md`, clear enough that implementation can
start without open questions. That version is a web page, opened on the
owner's phone, that runs the whole pipeline end to end (mic → speech-to-text →
decision model → fact-checking model → message-writing model → fact card on
screen) with provisional models behind the swappable interfaces `AGENTS.md`
requires, and includes development mode, so real dinners can be recorded as
**recording sessions** to start the **test corpus**.

## Notes

- **The output is a plan, not code.** Tickets resolve decisions; nothing here
  builds Carl. When the frontier is empty, assemble `spec.md` from the resolved
  tickets: that is arrival, not a ticket.
- **The product spec is settled.** [`.scratch/purpose-and-goal/spec.md`](../purpose-and-goal/spec.md)
  fixes behaviour and success criteria. Don't reopen it; if building proves a
  behaviour impossible, raise it with the owner. Its rationale lives in the
  [Purpose and goal map](../purpose-and-goal/map.md) and its tickets.
- **Provisional models only.** Pick models only as far as needed to build and
  record. The rigorous comparison is a later map (see Out of scope).
- **Hedge, don't refuse; precision over recall.** Finnish and English, fully.
- **Vocabulary:** use `CONTEXT.md` exactly (session, owner, table, utterance,
  candidate, claim, open question, verdict, fact card, hedged fact card, card
  history, card archive, late card, check time, failure log, monthly budget,
  recording session, test corpus). Grilling tickets also call
  `domain-modeling`; research tickets use the `research` skill.
- **Research** lives in `docs/research/`: start from
  [realtime-fact-checking.md](../../docs/research/realtime-fact-checking.md),
  [prior-art-live-fact-checking.md](../../docs/research/prior-art-live-fact-checking.md)
  (precision from concurrence and claim matching, not self-reported
  confidence) and [previous-carl-lessons.md](../../docs/research/previous-carl-lessons.md)
  (its stale, implementation-level lessons are relevant here: structured
  verdicts before anything renders, dedupe in Carl's own state, silent
  failures, one prompt source of truth, wake lock, no single-flight queue).
- **Git:** work directly on `main`; commit and push to `main`, no feature
  branches or pull requests (the owner's standing preference). Research
  findings go straight to `docs/research/` on `main`.

## Decisions so far

<!-- one line per resolved ticket: [title](issues/NN-slug.md): gist -->

## Not yet specified

- **Tracking a candidate until its card.** How Carl notices the table settling
  a claim or open question (drop before the card, "Settled at the table" after),
  how in-flight checks run concurrently, and how a late card is filed. Hangs on
  the decision model's context and de-duplication.
- **Location.** How the phone's precise location reaches the stages (raw
  coordinates or a place name, via which service, how often updated), and how
  it is rounded to neighbourhood or town for the test corpus.
- **Development mode vs normal mode.** Whether the dev version is a separate
  deployment, a switch, or a URL, and how the recording-session disclosure and
  objection flow look on screen.
- **Can't-hear-or-check state.** Which signals from each stage flip the
  listening indicator, and what the failure log records per stage.
- **Prompts and their one source of truth.** Where the decision,
  fact-checking and message-writing prompts live, how card language is
  chosen for mixed Finnish/English talk.
- **The screen.** Turning the [fact card prototype](../purpose-and-goal/prototypes/fact-card-prototype.html)
  into the real UI: Start screen, budget warning, card archive view, "Log" menu.
- **Build order.** How the plan slices into implementation steps once the
  architecture is decided.

## Out of scope

- **The rigorous vendor and model comparison** against the test corpus
  (word error rate, speaker attribution, precision/recall per stage, cost): a
  later, separate map that consumes the recordings this version makes.
- **A replay and scoring harness** for the test corpus: belongs with that
  comparison map. This version only has to record what a replay will need.
- **Writing the code.** This map ends at a plan.
- **Public-product concerns:** onboarding, billing, multi-tenant accounts.
