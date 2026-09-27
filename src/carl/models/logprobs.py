"""Choice probabilities from an LLM's token logprobs.

An LLM adapter asks for `{"answer": "<choice>"}` under a JSON schema and for
the top logprobs of each output token. Each choice's probability is read
from the tokens of the answer's value:

- At each token, the alternatives the model didn't take go to the choices
  they could start: `cl` to `claim`. An alternative that could start
  several choices differing only in their candidate id (`same` for `same as
  C1`, `same as C2`…) is pooled as `same as *`; one that could start
  several other choices is `ambiguous`; one that starts none, and any mass
  the top logprobs don't cover, is `other`.
- The walk follows the token the model took, as long as the answer so far
  could still be more than one choice. So when the model answers
  `same as C2`, the token that names the id also gives `same as C1`,
  `same as C3`… their own probabilities.
- The rest of the mass, once the answer is pinned down, is the chosen
  choice's.

This is exact for the path taken and approximate off it: an alternative's
whole mass goes to the choice it starts, as if the model would then
finish that choice.
"""

from __future__ import annotations

import math
import re
from collections.abc import Sequence

# One output token: (token, logprob, [(alternative, logprob)…]).
Step = tuple[str, float, Sequence[tuple[str, float]]]

VALUE_START = re.compile(r'"answer"\s*:\s*"')
CANDIDATE_ID = re.compile(r"\bC\d+\b")


def prob(logprob: float) -> float:
    """A logprob as a probability. Vendors return tiny positive logprobs for near-certain tokens."""
    return math.exp(min(0.0, logprob))


def matches(text: str, choices: Sequence[str]) -> list[str]:
    """The choices an answer's value could be, given its text so far.

    Text past a closing quote must match a choice exactly.
    """
    if '"' in text:
        value = text.split('"', 1)[0]
        return [c for c in choices if c == value]
    return [c for c in choices if c.startswith(text)]


def key(found: list[str]) -> str:
    """Where probability mass for these possible choices goes."""
    if len(found) == 1:
        return found[0]
    if not found:
        return "other"
    pooled = {CANDIDATE_ID.sub("*", c) for c in found}
    return pooled.pop() if len(pooled) == 1 else "ambiguous"


def answer_probs(steps: Sequence[Step], choices: Sequence[str]) -> dict[str, float] | None:
    """Each choice's probability, or None when the answer's value can't be found."""
    joined, starts = "", []
    for token, _, _ in steps:
        starts.append(len(joined))
        joined += token
    m = VALUE_START.search(joined)
    if not m:
        return None
    value_start = m.end()
    first = next((i for i, s in enumerate(starts) if s <= value_start < s + len(steps[i][0])), None)
    if first is None:
        return None
    probs: dict[str, float] = {}

    def add(k: str, p: float) -> None:
        if p > 0:
            probs[k] = probs.get(k, 0.0) + p

    reach = 1.0  # the probability of the path taken so far
    path = ""  # the value's text so far along that path
    for i in range(first, len(steps)):
        token, logprob, alternatives = steps[i]
        head = joined[starts[i]:value_start] if i == first else ""  # the token's part before the value
        seen = {token: logprob}
        for alt, alt_logprob in alternatives:
            seen.setdefault(alt, alt_logprob)
        covered = 0.0
        for alt, alt_logprob in seen.items():
            p = prob(alt_logprob)
            covered += p
            if alt != token:
                add(key(matches(path + alt[len(head):], choices)) if alt.startswith(head) else "other", reach * p)
        add("other", reach * max(0.0, 1.0 - covered))
        reach *= prob(logprob)
        path += token[len(head):]
        found = matches(path, choices)
        if len(found) <= 1:
            break
    add(key(found), reach)
    return probs
