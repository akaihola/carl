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
- **Set the previous Carl aside until our own research and planning are
  done.** Don't use its lessons in any ticket before *Check the previous
  Carl's lessons against our plan*, which compares them with the finished
  plan and keeps only what still applies.
- **Hedge, don't refuse.** Carl doesn't refuse to judge any category of claim
  (named people, quotes, unresolved pronouns). It conveys its confidence
  through its wording ("maybe", "probably"). This is the owner's standing
  preference for the prototype.
- Use the vocabulary in `CONTEXT.md` (decision model, candidate, claim, open
  question, verdict, fact card). Grilling tickets also call `domain-modeling`.
- Research lives in `docs/research/`; `docs/research/realtime-fact-checking.md`
  is the starting architecture research.
- **When the frontier is empty:** assemble `spec.md` from the resolved tickets
  and rewrite the Goal in `AGENTS.md`. That is arrival, not a ticket.

## Decisions so far

<!-- one line per resolved ticket: [title](issues/NN-slug.md): gist -->

- [Lessons from the previous Carl](issues/01-lessons-from-previous-carl.md): findings parked until *Check the previous Carl's lessons against our plan*
- [Prior art in live conversation fact-checking](issues/02-prior-art.md): no shipped product does exactly this; precision comes from two verifiers agreeing and from matching claims already checked, not from self-reported confidence (its refusal to judge risky claim types is overridden: Carl hedges instead); too much silence reads as broken
- [Situations Carl serves](issues/03-situations.md): home dinner or coffee, the owner plus 1–5 adults they know well, 2–6 speakers, one phone propped up for everyone to see, Finnish and English (mixed), running in the background for 30 min to 2 h
- [Edges of the purpose](issues/04-edges-of-purpose.md): only the two triggers; a card needs an error that changes the point (or a myth), a public-source-checkable claim and a citable source; confident verdicts stated plainly, likely ones hedged, lower ones silent; Carl drops what the table resolves itself and only overhears
- [Social contract at the table](issues/05-social-contract.md): everyone sees the same card; the owner discloses Carl and anyone's objection stops it; always-on listening indicator; anyone can pause with one tap; a card addresses the claim, never the person, in a neutral reference-book voice
- [Fact card behaviour](issues/06-fact-card-behaviour.md): one big card at a time (Spotlight) plus a Ledger-style card history; a card stays until tapped, and when others queue it gives way on a timer or a tap; cards the table settles on screen are marked settled; coloured Claim/Question labels, with hedged cards marked visually; live transcript line can be switched on and off; check time moves to *Success criteria*
- [Success criteria](issues/07-success-criteria.md): a test corpus built from recording sessions, each corrected by the owner, plus a log of real sessions; ≥95% of cards deserved and no wrong plain card; recall floors of 1 in 3 claims and 1 in 5 open questions; check time median ≤4 s and 90th percentile ≤8 s, with cards later than 20 s filed into the card history; about €1/h and a monthly cap
- [Session lifecycle and what Carl keeps](issues/09-session-lifecycle.md): the owner taps Start, anyone taps End, and a session also ends after 30 min without an utterance; a normal session keeps only its fact cards, in a card archive kept until the owner deletes it and opened only between sessions; development mode keeps cards, transcript, audio and full model-call logs for 6 months (overriding the earlier plan to delete raw logs); anyone at the table may see or delete what concerns them; no limit on providers, but the documentation and the suggested disclosure say where the conversation goes

## Not yet specified


## Out of scope

- Choosing vendors and models (speech-to-text, decision model, fact-checking
  model, message-writing model): a separate effort that consumes this spec's
  success criteria.
- Implementation architecture.
- Public-product concerns: onboarding, billing, multi-tenant accounts.
- Researching how people react to being corrected by a machine: Carl is an
  experiment, not a product.
