# Question

Carl overhears a conversation at a dinner or coffee table among people who
know each other well, in Finnish, English or both, and checks some of what is
said. `live_candidates` lists what it is checking right now, each with its id
as one standalone sentence. When a fact card for one of them is already on
screen, the card's fact follows it as "[on screen: …]". The card corrects
that candidate's claim or answers its question, so agreeing with the card
can mean taking the claim back. Does `utterance` settle one of them at the
table? Judge only `utterance`. `conversation` holds the lines said just
before it, so you can tell what it is about, and `date_time` says when the
table is. Each line starts with its speaker's label. A "(paused)" or "(gap)"
line marks a break in listening, after which the labels start afresh.

# Choices

- `settles Cn`: `utterance` settles Cn: it corrects Cn's claim, answers Cn's
  open question, or ends the disagreement in it, whether or not the answer is
  right, and even when Cn's own speaker corrects themselves. "Let's look it
  up", "I'm not sure" and more talk about the same topic settle nothing.
- `agrees with Cn`: `utterance` accepts the fact on Cn's card, or states the
  same fact or answer as the card, even when that takes back Cn's claim.
- `disputes Cn`: `utterance` rejects or doubts the fact on Cn's card, or
  sticks to Cn's claim against it.
- `none`: anything else.
