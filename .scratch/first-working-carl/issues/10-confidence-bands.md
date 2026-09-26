# Splitting verdict confidence into plain, hedged and silent

Type: grilling
Status: resolved
Blocked by: 07

## Question

How does a verdict's confidence map to a plain fact card, a hedged fact card or nothing, given that a single model's self-reported confidence is not usable on its own? E.g. two verifiers agreeing, a required citable source, source quality rules, categories held back, fixed provisional thresholds to be tuned later on the test corpus.

## Comments

- From [Provisional models for each stage](07-provisional-models.md#answer): the verdict is now the fact-checking model's typed judgement of a draft card, with a probability per choice (Jev natively; logprobs for the Gemini swap). Two fact-finders (GPT-6 Luna and Gemini 3.8 Flash) write draft cards in parallel. With no text generated after fact-checking, a hedged fact card's "probably"/"maybe" must come from a fixed hedge form or mark rather than from rewriting.
- From [Search providers' terms and Luna web search](17-search-terms-and-luna.md#answer): OpenAI's citations carry no source text, so fact-finder A's excerpt is written by the model and can't be matched against the source without fetching the page; Perplexity's `search_results` snippets can be matched word for word. Decide whether an unmatched excerpt can still reach a plain card.
- From [Decision model context and candidate de-duplication](09-decision-context-and-dedup.md#answer): the decision model has its own two config thresholds (repeat 0.5, candidate 0.5), falling back to the chosen answer when there are no probabilities. The fact-checking model is judged against the original utterance, not the fact-finder's restatement.

## Answer

Settled with the owner in a grilling session (2026-09-26).

**The signal is agreement plus Carl's own excerpt check**, never one model's
self-reported confidence. See `CONTEXT.md` for **agreement** and **verified
excerpt**.

**Gathering the evidence**

1. **Wait for both fact-finders, with a deadline.** Carl waits for both draft
   outcomes until **~12 s after the first one arrives** (config). A
   fact-finder that fails or misses the deadline leaves the other judged
   alone. Rejected: showing the first card and later confirming or
   withdrawing it (a contradiction on screen costs trust).
2. **Excerpt verification.**
   - Fact-finder B (Perplexity): its excerpt must be a substring of a
     `search_results` snippet from the same URL.
   - Fact-finder A (OpenAI): the server downloads the source URL (timeout
     ~3 s, config) and looks for the excerpt after normalising whitespace and
     quotes.
   - A match is a **verified excerpt**. A failed download or a miss leaves
     the card unverified; that is not a failure-log entry.
3. **Source quality:** a small **blocklist** in config (forums and Q&A sites
   such as Reddit and Quora, social media, video platforms, user-edited wikis
   other than Wikipedia). A blocklisted source counts as no citable source.
   The fact-finders' prompts also ask them to prefer primary or reference
   sources. No allowlist, since it would silence situational questions.
4. **Verdicts:** the fact-checking model judges each draft card separately
   (`supported / not supported / doesn't answer the candidate`).
5. **Agreement call:** when both fact-finders return the same outcome (both
   `claim is wrong` or both `question answered`), one more typed call to the
   fact-checking model asks `same fact / compatible but different /
   contradict`, given the candidate and both cards. It runs alongside the
   verdicts.
   - **same fact** → agreement.
   - **compatible but different** → no agreement; each card is judged alone.
   - **contradict** (1954 vs 1955) → nothing shown.
   - `claim is wrong` vs `claim is right` is a contradiction without asking.
   - `wrong`/`answered` vs `not found` (or a failed fact-finder) → one card
     alone.

**The bands** (starting thresholds, in config, stored with each recording
session, tuned later on the test corpus):

| Band | Needs |
| --- | --- |
| **Plain fact card** | Agreement with p(same fact) ≥ 0.7; the shown card has a verified excerpt, a non-blocklisted source and p(supported) ≥ 0.85; the other card p(supported) ≥ 0.5 |
| **Hedged fact card** | A card with a verified excerpt, a non-blocklisted source and p(supported) ≥ 0.6, and no contradiction from the other fact-finder. Covers a single fact-finder's card and an agreeing pair short of the plain bar |
| **Nothing** | Everything else, and any contradiction |

- **A shown card always has at least one verified excerpt behind it.** An
  unverified card can only be the second, agreeing card.
- **Which card is shown:** the verified one; if both are verified, the one
  with the higher p(supported).
- **No probabilities** (a fact-checking model without logprobs): `supported`
  counts as meeting the hedged threshold only, so the card is capped at
  hedged even with agreement.
- **No categories held back or capped** (health, time-sensitive facts…): the
  spec rules out refusal by category, and a cap would be one in disguise.

**The hedge wording.** One hedge level. A fixed word goes before the checked
sentence, which stays exactly as it was judged: "Todennäköisesti: …" /
"Probably: …", plus the visual mark. The spec's "maybe" is dropped for now: a
second level would claim a finer split than Carl can measure. Rejected: a
second, hedged sentence written by the fact-finder (unchecked text on screen,
and a fragile Finnish word diff).

**What the recording keeps** for each candidate that reaches fact-checking:
both draft cards, both verdicts with probabilities, the agreement call, A's
download result, B's snippet match, any blocklist hit, and the band with a
**reason code** (e.g. `plain:agreed`, `hedged:single-verified`,
`silent:contradiction`, `silent:unverified`), so the comparison map can tune
thresholds without replaying the calls.
