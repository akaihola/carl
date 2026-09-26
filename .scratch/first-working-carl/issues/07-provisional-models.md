# Provisional models for each stage

Type: grilling
Status: resolved
Blocked by: 01, 02, 03, 06, 15

## Question

Which provider and model does the first working version use for speech-to-text, the decision model, the fact-checking model and the message-writing model, and what does each stage's provider-neutral interface look like (inputs, outputs, errors) so it can be swapped through configuration?

## Comments

- Owner's steers from [What "done" means for the first working version](01-done-for-first-version.md#answer): see its answer.

## Answer

Settled with the owner in a grilling session (2026-09-25/26).

**The pipeline changes shape.** There is no message-writing model:

```
mic → speech-to-text → decision → fact-finding → fact-checking → card on screen
```

The decision and fact-checking models give **typed answers only**, so that
Jev-like models fit. The new **fact-finding model** searches the web and
writes the **draft card**. See `CONTEXT.md` for the terms and
[ADR 0001](../../../docs/adr/0001-typed-judges-around-a-writing-search.md)
for why.

**Provisional models:**

| Stage | Provisional | Swap |
| --- | --- | --- |
| Speech-to-text | Soniox stt-rt-v5 (~$0.12/h) | AssemblyAI later, with the comparison map |
| Decision model | GPT-6 Luna, typed JSON schema, reasoning off (~$0.06/h) | TypeSafe Jev, in the comparison map |
| Fact-finding model, A | GPT-6 Luna with OpenAI web search | Luna on the Perplexity Agent API if OpenAI's web search doesn't serve Luna (its guide doesn't list it; the models page does) |
| Fact-finding model, B | Perplexity Agent API, model pinned to `gemini-3.8-flash`, Perplexity `web_search` ($2.50/1,000) | – |
| Fact-checking model | TypeSafe Jev | Gemini 3.5 Flash-Lite, typed, with logprobs, called directly (no grounding) |

- **No Anthropic models:** the owner's subscription can't be used for API calls.
- **Google Search grounding stays out**, because its terms forbid storing and
  analysing grounded results. Gemini through Perplexity's search, and plain
  Gemini without grounding, are not grounded results.
- **The two fact-finders run in parallel** on every candidate. They use
  different model vendors (OpenAI and Google) and different search engines
  (OpenAI and Perplexity). Pinning the model avoids the `fast` preset changing
  its model under Carl. How their agreement and the verdict's probability
  become a plain, hedged or no card is left to
  [Splitting verdict confidence into plain, hedged and silent](10-confidence-bands.md).
- **Parakeet and Nemotron are not in the first version.** The recorded audio
  lets the comparison map replay Nemotron later.
- **Estimated running cost:** about $0.35–0.55/h at 10–20 candidates an
  hour: speech-to-text $0.12, decision $0.06, fact-finder A $0.11–0.22,
  fact-finder B $0.06–0.12, fact-checking under a cent.
- **Open facts** went to
  [Search providers' terms and Luna web search](17-search-terms-and-luna.md).

**Stage interfaces** (provider-neutral):

- **Speech-to-text:**
  - `open(languages [fi, en], audio format)` returns a stream of interim and
    final events, with words carrying a speaker label, start and end.
  - `close()` ends the stream.
  - Splitting finals into utterances happens in the pipeline, not the adapter.
- **Typed-answer interface**, shared by the decision and fact-checking models:
  - Input: named text fields, one question, and an answer type: a choice from a
    list given in the input, a boolean, or a score in a stated range.
  - Output: the answer and a probability per choice (or per true/false).
    LLM adapters use a JSON schema limited to the given choices; probabilities
    come from logprobs where the vendor has them, and are empty otherwise.
  - The decision model asks `none / claim / open question` about the new
    utterance, given recent utterances, date, time and location.
  - The fact-checking model asks `supported / not supported / doesn't answer
    the candidate` about a draft card, given the candidate, the card and its
    source excerpt.
- **Fact-finding model:**
  - Input: the candidate, its context, date, time and location.
  - Output: an outcome, `claim is wrong / claim is right / question answered /
    not found`.
  - For `claim is wrong` and `question answered`, it also returns a draft
    card: title, one-sentence fact, source URL and title, and a verbatim
    source excerpt supporting the fact.
  - `claim is right` and `not found` end the candidate silently.
- **Every call** also returns model id, prompt version, parameters, tokens,
  cost and latency (for recording and metering), or on error a typed error:
  timeout, unavailable, rate-limited, or bad output.
  - Adapters never retry. The pipeline decides what to do with an error and
    writes it to the failure log.

**Swapping models:** a config file in the repo maps each stage to its provider,
model and parameters, with keys held as server secrets. A change means a
redeploy. Each recording session stores the config it ran with, so a replay
knows what ran. Runtime switching belongs to the comparison map.
