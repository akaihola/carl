# A card needs a verified excerpt even when both fact-finders agree

Every fact card Carl shows has at least one excerpt that Carl itself found word
for word in its source, even when both fact-finders reach the same correction
and the agreement call says `same fact` at 1.0. In the test corpus two
deserved corrections stayed silent for want of one (e825e8 C2, Chile's
capital: A's source answered 403 and B's excerpt wasn't in its snippets;
bf362b C2, Sweden's capital: A's excerpt was too short and B's wasn't in its
snippets). We keep the rule and verify more instead: B's excerpt is looked for
on its downloaded page when the snippets miss it, and A's on its other result
pages when its own page can't be read. A card shown on agreement alone would be
one no fact-checking model had judged: `needs_verdict` asks for no verdict when
neither card could be shown, and the agreement call compares two cards, never
a source. Two finders can also repeat the same wrong fact from the same
popular page.

## Considered Options

- A hedged card when both finders agree at `same fact` 1.0 but neither
  excerpt is verified, with verdicts asked anyway. Rejected: an unverified
  excerpt may not exist, so the verdict would judge the card against text
  nobody has seen, and "never surface unsourced verdicts" (`AGENTS.md`) is
  the product's first rule.
- The same, only for sources on a short allowlist (Wikipedia, Britannica).
  Rejected for the same reason: the allowlist says where the excerpt claims
  to come from, not that it is there.
- An exception to the 20-character, 3-word minimum for "label: value"
  excerpts such as "Capital: Stockholm". Rejected: a short excerpt proves
  little on a long page, and in bf362b C2 B's fi.wikipedia excerpt was there
  to be verified on its page.
