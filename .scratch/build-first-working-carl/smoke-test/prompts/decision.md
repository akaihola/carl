# Question

Carl overhears a conversation at a dinner or coffee table among people who
know each other well, in Finnish, English or both. Is `utterance` worth
fact-checking? Judge only `utterance`. `conversation` holds the lines said
just before it, so you can tell what it is about, and `place_and_time` says
where and when the table is.

# Choices

- `claim`: `utterance` states something that can be checked as true or false
  against a public source, given where and when the table is. Opinions,
  predictions, jokes, private facts ("I was there in 2019") and contested
  questions are not claims.
- `open question`: `utterance` wonders about something a public source can
  answer, given where and when the table is, and nobody has answered it yet
  ("what was that actor's name…", "1953 or '54?").
- `same as Cn`: `utterance` asserts the same thing, or asks the same
  question, as the earlier candidate Cn in `earlier_candidates`, in any
  language or wording. The same topic is not enough: "He did fail maths,
  though" is the same as "Einstein failed maths", but "He failed physics,
  actually" is a new claim.
- `none`: anything else, including when you can't tell from `conversation`
  what a claim in `utterance` is about.
