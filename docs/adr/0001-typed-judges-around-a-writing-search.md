# Cards are written by search before they are checked, and the judges only give typed answers

Carl has no message-writing stage. The fact-finding model searches the web and
writes the draft card itself, and a separate fact-checking model then judges
that draft against its source excerpt. Both the decision model and the
fact-checking model give only typed answers (a choice from a list given in the
input, a boolean or a score, with a probability for each) and never write text.
We chose this so that the two judging stages can run on cheap classifier-style
models such as TypeSafe Jev, whose native probabilities are the confidence
signal that LLMs' self-reported confidence can't give, and so that nothing a
checker writes can reach the screen unchecked.

## Considered Options

- Decision → fact-checking (search, returns a verdict) → message writing
  (verdict to card), as first sketched in `AGENTS.md`. Rejected: two
  text-writing stages after the search, and no stage that judges the final
  wording.
