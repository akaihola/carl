# Question

A web search wrote a draft card (`card_title`, `card_fact`) to correct the
claim in `candidate`, or to answer its open question, and copied `excerpt`
from its source to back it. `conversation` holds the lines said at the table
just before `candidate`, each starting with its speaker's label, and
`date_time` says when the table is. Judge the card against `excerpt` only,
not against what you know yourself. The card and the excerpt may be in
different languages (Finnish or English); judge them as they are.

# Choices

- `supported`: `card_fact` corrects the claim in `candidate` or answers its
  question, and `excerpt` states what `card_fact` says. It may say more.
- `not supported`: `excerpt` doesn't state what `card_fact` says, states
  something else, or contradicts it.
- `doesn't answer the candidate`: `card_fact` doesn't correct the claim in
  `candidate` or answer its question, whether or not `excerpt` supports it.
