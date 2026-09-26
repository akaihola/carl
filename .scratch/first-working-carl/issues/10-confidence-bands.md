# Splitting verdict confidence into plain, hedged and silent

Type: grilling
Status: open
Blocked by: 07

## Question

How does a verdict's confidence map to a plain fact card, a hedged fact card or nothing, given that a single model's self-reported confidence is not usable on its own? E.g. two verifiers agreeing, a required citable source, source quality rules, categories held back, fixed provisional thresholds to be tuned later on the test corpus.

## Comments

- From [Provisional models for each stage](07-provisional-models.md#answer): the verdict is now the fact-checking model's typed judgement of a draft card, with a probability per choice (Jev natively; logprobs for the Gemini swap). Two fact-finders (GPT-6 Luna and Gemini 3.8 Flash) write draft cards in parallel. With no text generated after fact-checking, a hedged fact card's "probably"/"maybe" must come from a fixed hedge form or mark rather than from rewriting.
- From [Search providers' terms and Luna web search](17-search-terms-and-luna.md#answer): OpenAI's citations carry no source text, so fact-finder A's excerpt is written by the model and can't be matched against the source without fetching the page; Perplexity's `search_results` snippets can be matched word for word. Decide whether an unmatched excerpt can still reach a plain card.
- From [Decision model context and candidate de-duplication](09-decision-context-and-dedup.md#answer): the decision model has its own two config thresholds (repeat 0.5, candidate 0.5), falling back to the chosen answer when there are no probabilities. The fact-checking model is judged against the original utterance, not the fact-finder's restatement.
