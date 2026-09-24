# Map: Purpose and goal of Carl

Label: wayfinder:map

## Destination

A product spec at `.scratch/purpose-and-goal/spec.md` stating what Carl is for,
who uses it, the situations it serves, what it deliberately doesn't do, and how
we'd know it works. `AGENTS.md`'s Goal section is rewritten from it.

## Notes

- **Carl is an experiment, not a product.** Private, personal use: the owner
  plus whoever is at their table. Keep this as a deliberate limit.
- Working hypothesis: the two triggers in `AGENTS.md` (a false claim; an
  unanswered open question) are the core purpose. *Edges of the purpose* tests
  whether anything else belongs.
- Treat findings from the previous Carl critically: the model and vendor
  landscape has changed a lot since it was built.
- Use the vocabulary in `CONTEXT.md` (decision model, candidate, claim, open
  question, verdict, fact card). Grilling tickets also call `domain-modeling`.
- Research lives in `docs/research/`; `docs/research/realtime-fact-checking.md`
  is the starting architecture research.
- **When the frontier is empty:** assemble `spec.md` from the resolved tickets
  and rewrite the Goal in `AGENTS.md`. That is arrival, not a ticket.

## Decisions so far

<!-- one line per resolved ticket: [title](issues/NN-slug.md): gist -->

- [Lessons from the previous Carl](issues/01-lessons-from-previous-carl.md): stay silent by default, keep to the two triggers, give the table time before showing a card, drop overtaken verdicts; the model-specific tricks are stale
- [Prior art in live conversation fact-checking](issues/02-prior-art.md): no shipped product does exactly this; precision comes from agreeing verifiers, checked-claim matching and never showing risky claim types, not self-reported confidence; too much silence reads as broken

## Not yet specified

- **Session lifecycle.** How a session starts and stops, and whether Carl
  leaves anything behind afterwards (e.g. a post-conversation recap of what
  was checked). Sharpens once *Social contract at the table* is resolved.
- **Privacy beyond "in memory only".** What, if anything, may be kept, and
  what the others at the table are entitled to.

## Out of scope

- Choosing vendors and models (speech-to-text, decision model, fact-checking
  model, message-writing model): a separate effort that consumes this spec's
  success criteria.
- Implementation architecture.
- Public-product concerns: onboarding, billing, multi-tenant accounts.
- Researching how people react to being corrected by a machine: Carl is an
  experiment, not a product.
