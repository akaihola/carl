# Question

A search wrote a draft card (`card_title`, `card_fact`) to correct the claim
in `candidate`, or to answer its open question. `conversation` holds the
lines said just before `candidate`. Judge the card against its source
excerpt `excerpt` only, not against what you know yourself. The card and the
excerpt may be in different languages (Finnish or English); judge them as
they are.

# Choices

- `supported`: `excerpt` states what `card_fact` says. It may say more.
- `not supported`: `excerpt` doesn't state what `card_fact` says, states
  something else, or contradicts it.
- `doesn't answer the candidate`: `card_fact` doesn't correct the claim in
  `candidate` or answer its question, whether or not `excerpt` supports it.
