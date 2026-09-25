# Models for the decision, fact-checking and message-writing stages

Research for the ticket *Models for the decision, fact-checking and
message-writing stages*
(`.scratch/first-working-carl/issues/03-models-for-text-stages.md`), compiled
2026-09-25. It builds on [realtime-fact-checking.md](realtime-fact-checking.md)
(architecture and vendor landscape) and
[prior-art-live-fact-checking.md](prior-art-live-fact-checking.md) (how
Footnote and others keep precision high). The spec's targets are a check time
of median ≤ 4 s and 90th percentile ≤ 8 s, and a running cost of about €1 per
hour of listening for all stages together.

## How this was researched, and how far to trust it

- Prices, features and limits were read on each vendor's own pricing and
  documentation pages on 2026-09-25. Those claims are marked **[verified]**.
  Prices change often; re-read the page before relying on a figure.
- **[vendor]** marks self-reported claims, such as speed and quality, that
  nobody has measured independently.
- **[probed]** marks browser-access facts found by sending a CORS preflight
  request (`OPTIONS` with an `Origin` header) to each API on 2026-09-25. A
  preflight shows whether a browser *may* call the API. It says nothing about
  whether it is *safe* to.
- **[estimate]** marks this note's own arithmetic. The assumptions are listed
  in [Cost per hour](#cost-per-hour-estimate).
- **No model was called.** The research environment had no API keys, so
  there are no measured response times, and nothing here shows how well any
  model handles Finnish. No vendor publishes a Finnish benchmark for these
  models (see [Finnish](#finnish)).
- All prices are in US dollars, as the vendors publish them. At the time of
  writing, €1 is roughly $1.1–1.2; check the day's rate.

## Summary

1. **The cost target rules out a mid-size model for the decision model.** At
   about 600 utterances an hour, Claude Haiku 4.5 alone costs about
   $0.60/h [estimate], and Claude Sonnet 5 about $1.25/h. The cheap tier
   costs a few cents an hour: GPT-6 Luna, Gemini Flash-Lite, gpt-oss on Groq,
   and TypeSafe Jev (input tokens only, at $0.042 per million).
2. **Search dominates the fact-checking model's cost, not tokens.** A search
   costs $2.50–$14 per 1,000, depending on the vendor. With Claude's and
   OpenAI's search, the search results are also billed as input tokens. At
   10–20 candidates an hour, the fact-checking model costs between a few
   cents an hour (Gemini within its free search allowance, or Perplexity's
   Agent API) and about $0.90/h (Claude Sonnet 5 with web search).
3. **No vendor publishes a response time for a search-grounded answer.** The
   only published figure is Exa's `deep-lite` search, at about 4 s
   [vendor]. Whether any option meets median ≤ 4 s has to be measured.
4. **Usable confidence signals are thin.**
   - Gemini's grounding metadata has per-segment support scores, documented
     as "Optional".
   - OpenAI and Gemini expose token log probabilities.
   - Claude exposes neither. Its web search returns cited text instead.
   - None of these is a calibrated verdict confidence. Footnote's result, that
     two fact-checking calls must agree, remains the documented way to get a
     usable signal.
5. **Perplexity's Sonar API ends on 2026-09-27**, two days after this note.
   Its replacement, the Agent API, has a `fast` preset: one step, one web
   search, GPT-6 Luna. That preset is the cheapest search-grounded option
   found, at about $0.003 per call [estimate].
6. **Google's search terms constrain Carl.** Grounded results must be shown
   with Google's "Search Suggestions". They may not be stored or analysed
   beyond narrow exceptions, and results that are not shown must be deleted.
   This conflicts with recording sessions and the test corpus.
7. **Every API checked answers a browser's CORS preflight**, except that Exa's
   answer is unclear. No vendor offers short-lived browser keys for these
   text APIs: OpenAI's and Google's ephemeral keys cover only their realtime
   and live voice APIs. Every vendor's own guidance is to keep the key on a
   server.

## Decision model

What it needs: cheap enough to run on every utterance; fast (a few hundred
milliseconds); structured output (candidate yes/no, claim or open question);
Finnish and English.

| Model | Price per 1M tokens (in / out) | Structured output | Speed signal | Notes |
| --- | --- | --- | --- | --- |
| Claude Haiku 4.5 (`claude-haiku-4-5`) | $1 / $5 [verified] | Yes (JSON schema) [verified] | "Fastest" of Claude's lineup, relative only [vendor] | Prompt caching needs at least 4,096 tokens of prefix, so a short decision prompt cannot be cached [verified]. |
| Gemini 3.5 Flash-Lite (`gemini-3.5-flash-lite`) | $0.30 / $2.50 [verified] | Yes | "Fastest, most cost-effective 3.5 model" [vendor] | Google's recommended high-volume model. |
| Gemini 3.1 Flash-Lite (`gemini-3.1-flash-lite`) | $0.25 / $1.50 [verified] | Yes | Not published | Previous generation, still offered. |
| GPT-6 Luna (`gpt-6-luna`) | $0.10 / $0.50 [verified] | Yes [verified] | "Most efficient option for focused, high-volume operations" [vendor] | Reasoning can be set to `none` [verified]. |
| gpt-5-nano | $0.05 / $0.40 [verified] | Yes | Not published | Older generation, cheapest OpenAI option. |
| gpt-oss-20b on Groq | $0.075 / $0.30 [verified] | JSON mode (OpenAI-compatible API) | 1,000 tokens/s [vendor] | Open-weight. |
| gpt-oss-120b on Groq | $0.15 / $0.60 [verified] | JSON mode | 500 tokens/s [vendor] | |
| gpt-oss-120b on Cerebras | $0.35 / $0.75 [verified] | JSON mode | ~3,000 tokens/s [vendor] | |
| Qwen 3.8 27B on Groq / Cerebras | $0.80 / $4.00 (Groq), $0.99 / $1.49 (Cerebras) [verified] | JSON mode | 450 / ~1,850 tokens/s [vendor] | Preview on Groq ("evaluation only"). |
| TypeSafe Jev 1.13 (`jev-1.13.0`) | $0.042 per 1M **input** tokens; output is free [verified] | Typed answers only (Choice, Score, Noul) with probabilities and confidence [verified] | "~100× faster" than LLMs [vendor, from the earlier note] | Rate limits of 250k tokens/s and 1,200 requests/min "are adjusting dynamically" [verified]. |

Notes:

- **Groq and Cerebras** serve only a few general models: GPT OSS 20B/120B and
  Qwen 3.8 27B; Llama models are "Contact Sales" on Groq. Their advantage is
  generation speed, which matters little for a decision model that writes
  about 40 tokens. Time to first token is not published.
- **Jev** fits the decision model's job, independent questions answered with
  a probability, better than a text generator does. Its documentation says
  "English is the primary training language … Other languages … are handled
  but not equally well; test on your own content before relying on Jev for a
  non-English workload" [verified]. It does not publish a response time.
- **Output size** matters little here. At about 40 output tokens per call,
  every model's cost is driven by input: the system prompt, a few lines of
  context and the utterance.

## Fact-checking model

What it needs: web search or grounding with citable sources; a structured
verdict (outcome, answer, source, confidence); a check time within median 4 s
and 90th percentile 8 s, measured end to end; and a confidence signal worth
trusting.

### Options

**Claude with the web search tool** [verified]

- Price: $10 per 1,000 searches, plus token costs. Search results are billed
  as input tokens.
- Search tool versions:
  - Haiku 4.5 supports only the basic `web_search_20250305`.
  - Sonnet 5, Opus 5.5 and other Claude 4.6+ models add dynamic filtering
    (`web_search_20260209` and later). Claude writes code that trims the
    results before they enter the context, which lowers the tokens billed.
    That code runs at no extra charge.
- Controls: `max_uses` caps searches per request ("simple factual queries
  typically use 1–3 searches"), and `allowed_domains`/`blocked_domains` and
  `user_location` shape the search.
- Citations are always on. Each one carries the URL, title and up to 150
  characters of cited text, and the cited text is not billed.
- Structured outputs (`output_config.format`) return a 400 error when
  citations are enabled on documents. The docs do not say whether that
  applies to web search citations, so this is **unverified**. A strict tool
  for the verdict, or a second call, may be needed.
- There are no logprobs: the Messages API has no such parameter.
- Model prices per 1M tokens (in / out):
  - Sonnet 5: $2 / $10. The $2/$10 launch price is now the standard price.
  - Opus 5.5: $4 / $20.
  - Haiku 4.5: $1 / $5.

**Gemini with Grounding with Google Search** [verified]

- Price: 5,000 search queries a month free, then $14 per 1,000. For Gemini 3
  models, Google bills "each search query that the model decides to execute",
  so one prompt can be billed for two queries.
- Model prices per 1M tokens (in / out):
  - Gemini 3.8 Flash: $0.75 / $3.75 until 2026-12-31, then $1.50 / $7.50.
  - Gemini 3.1 Pro (preview): $2 / $12.
  - Flash-Lite: see the decision model table.
- Structured output combined with Search grounding is a preview feature for
  Gemini 3 models only.
- The `GroundingSupport` object maps segments of the answer to source chunks.
  It has a `confidenceScores` field ("0 to 1 … This list must have the same
  size as the groundingChunkIndices"), marked Optional; whether current
  models fill it is **unverified**.
- The API also offers `responseLogprobs` and `avgLogprobs`.
- **Terms of use:** the Gemini API terms say grounded results may be shown
  only "with the associated Search Suggestion(s) to the end user who
  submitted the prompt". Developers may not "cache, frame, syndicate, resell,
  analyze, train on, or otherwise learn from Grounded Results". Storage is
  allowed only for narrow purposes, up to two years; results not shown must
  be deleted.

**OpenAI with the web search tool** [verified]

- Price: $10 per 1,000 calls, plus "search content tokens billed at model
  rates".
- Model prices per 1M tokens (in / out):
  - GPT-6 Sol: $2 / $10.
  - GPT-6 Astra: $10 / $50.
  - GPT-6 Luna: $0.10 / $0.50.
- Supported models: the models page lists web search for all three GPT-6
  models, but the web search guide names only `gpt-6-astra`, `gpt-5.5`,
  `gpt-4.1` and `gpt-4.1-mini`. Which is current is **unclear**.
- Modes: non-reasoning search is "fast and ideal for quick lookups", and
  agentic search "take[s] longer".
- Citations come back as `url_citation` annotations, which "must be made
  clearly visible and clickable". `search_context_size` (low/medium/high),
  `user_location` and up to 100 allowed or blocked domains are supported.
- Token logprobs are available with
  `include: ["message.output_text.logprobs"]`. The reference does not say
  which models return them.

**Perplexity** [verified]

- Sonar Chat Completions "will be supported until September 27, 2026" and is
  replaced by the Agent API. Sonar's last prices per 1M tokens: Sonar $1 / $1
  plus $5–12 per 1,000 requests; Sonar Pro $3 / $15 plus $6–14 per 1,000
  requests.
- The Agent API is Open Responses-compatible and serves OpenAI, Anthropic,
  Google and other models at the vendors' own token prices. Its web search
  costs $2.50 per 1,000 calls, or $1 per 1,000 with `search_type: "fast"`.
  Fetching a URL costs $0.50 per 1,000.
- Its `fast` preset is a single-step search with GPT-6 Luna, no reasoning and
  priority service tier, and is meant for "quick factual lookups with
  minimal latency". The pricing widget still names `gpt-5.6-luna`, so the
  model behind the preset may change.
- Perplexity's own benchmark puts the `fast` preset at 28.0 on BrowseComp
  against 7.0 for Sonar, at a similar cost per 1,000 [vendor].
- Structured outputs are supported.

**Search API plus your own model** [verified]

- Exa `/search` costs $7 per 1,000 requests (up to 10 results), plus $1 per
  1,000 pages of contents. `/answer` costs $5 per 1,000. `deep-lite` costs
  $12 per 1,000 at "~4 seconds" [vendor].
- Tavily basic search costs 1 credit, advanced 2 credits, at $0.008 per
  credit pay-as-you-go ($5–7.50 per 1,000 on monthly plans). 1,000 credits a
  month are free.
- Perplexity Search API costs $5 per 1,000, or $1 per 1,000 for fast search.
- Carl then calls a model of its choice with the results. This makes two
  network round trips instead of one, but Carl controls the prompt, the
  sources passed in and the structured output, and can reuse the same
  results for two independent fact-checking calls.
- **Groq Compound** (Groq's built-in search) was deprecated on 2026-09-21
  [verified].

### Speed against the check time target

No vendor publishes how long a search-grounded answer takes. What is
published:

- Claude's comparative speed is relative only.
- OpenAI says non-reasoning search is "fast" and agentic search takes longer.
- Perplexity's `fast` preset is tuned for "minimal latency" and runs on a
  priority tier.
- Exa's `deep-lite` takes about 4 s.

The check time also includes the speech-to-text final segment and the
decision model before this call, and the message-writing model and rendering
after it. A single model call with one search round and a short answer is the
shape most likely to fit median ≤ 4 s. Multi-search or reasoning modes are
likely to push the 90th percentile past 8 s. This needs measuring on the test
corpus.

### Confidence signals

| Signal | Where it exists | What it measures |
| --- | --- | --- |
| Token log probabilities | OpenAI (`output_text.logprobs`), Gemini (`responseLogprobs`, `avgLogprobs`) [verified]; not Claude [verified] | How sure the model was of each output token. It is not evidence strength, and a verdict word's probability can be high while the evidence is wrong. |
| Grounding support scores | Gemini `groundingSupports[].confidenceScores` [verified, marked Optional] | How well a sentence is backed by a retrieved chunk. Closest to "is this sourced", but whether it is filled is unverified. |
| Cited text | Claude `cited_text`, OpenAI `url_citation`, Perplexity `search_results` [verified] | Lets Carl check in code that a source exists and quotes the answer. It is a precondition, not a confidence. |
| Model-stated confidence | Any model, via the structured verdict | Footnote found that a single model's stated confidence "saturated (0.97–0.99 on nearly everything)" [code, from the prior-art note]. |
| Two fact-checking calls agreeing | Any pair of calls, ideally different vendors | Footnote's concurrence rule: both must return the same definitive verdict, and confidence is the lower of the two. It reported mean confidence of 0.95 when right and 0.60 when wrong [code, from the prior-art note]. It doubles the fact-checking cost. |

## Message-writing model

What it needs: a title and one sentence, in Finnish or English, in an
encyclopedic register. The input is the verdict (about 300–500 tokens) and
the output is about 60–100 tokens.

- **Any capable model will do; cost is not a concern here.** At about 500
  tokens in and 80 out, one fact card costs about $0.0009 with Haiku 4.5,
  $0.0018 with Sonnet 5, $0.0007 with Gemini 3.8 Flash and $0.0001 with
  GPT-6 Luna [estimate]. Even at 20 cards an hour this is under $0.04/h.
- **Writing speed matters more than price.** Output is short, so time to the
  first token dominates. Groq and Cerebras have the highest generation speed
  [vendor], but gpt-oss's Finnish writing quality is unknown.
- **The fact-checking model could write the fact card itself.** It would
  return the title and sentence as fields of the structured verdict, which
  removes one call from the check time. The spec keeps the message-writing
  model as its own stage; merging the two is a design choice this note does
  not make.

## Finnish

- No candidate vendor publishes Finnish scores. Anthropic's multilingual table
  (MMLU translated into 14 languages) covers Haiku 4.5 and Sonnet 4.5 but not
  Finnish. Haiku 4.5 is at 94–96% of English on the European languages
  listed [verified]. TypeSafe says non-English is weaker for Jev [verified].
  Google, OpenAI, Groq and Cerebras publish no per-language numbers on the
  pages read.
- Finnish takes more tokens per word than English in most tokenizers. That
  raises every per-call figure below for Finnish speech, by an amount that
  has to be measured.
- **Search quality in Finnish** matters as much as the model's Finnish. The
  table's questions are often local (Finnish politics, places, sport), so
  sources such as Yle and Finnish Wikipedia need to be reachable. Claude,
  OpenAI and Perplexity accept a `user_location` or domain filter.

## Cost per hour (estimate)

Assumptions [estimate]:

- **Decision model:** 600 calls an hour, each with about 850 input tokens
  (a 600-token prompt, about 200 tokens of recent context and a 50-token
  utterance) and about 40 output tokens. No caching: the prompt is below
  Claude Haiku's 4,096-token minimum.
- **Fact-checking model:** 10–20 candidates an hour, each with one search.
  Where results are billed as tokens, about 15,000 input tokens per call
  (Claude basic search) or 8,000 (OpenAI), and 500 output tokens. Gemini is
  assumed to bill only prompt and output tokens (about 2,000 in, 500 out)
  plus the query fee.
- **Message-writing model:** as above; under $0.04/h for every option, and
  left out of the totals.

| Decision model | Per call | Per hour (600 calls) |
| --- | --- | --- |
| Claude Sonnet 5 (for comparison) | $0.0021 | ~$1.26 |
| Claude Haiku 4.5 | $0.0011 | ~$0.63 |
| Gemini 3.5 Flash-Lite | $0.00036 | ~$0.21 |
| Cerebras gpt-oss-120b | $0.00033 | ~$0.20 |
| Gemini 3.1 Flash-Lite | $0.00027 | ~$0.16 |
| Groq gpt-oss-120b | $0.00015 | ~$0.09 |
| GPT-6 Luna | $0.00011 | ~$0.06 |
| Groq gpt-oss-20b | $0.00008 | ~$0.05 |
| gpt-5-nano | $0.00006 | ~$0.04 |
| TypeSafe Jev | $0.00004 | ~$0.02 |

| Fact-checking model (one search per call) | Per call | Per hour (10–20 calls) |
| --- | --- | --- |
| Claude Opus 5.5 + web search | ~$0.080 | $0.80–1.60 |
| Claude Sonnet 5 + web search | ~$0.045 | $0.45–0.90 |
| OpenAI GPT-6 Sol + web search | ~$0.031 | $0.31–0.62 |
| Claude Haiku 4.5 + basic web search | ~$0.028 | $0.28–0.55 |
| Gemini 3.8 Flash + Search, past the free 5,000 queries | ~$0.017 | $0.17–0.35 |
| OpenAI GPT-6 Luna + web search | ~$0.011 | $0.11–0.22 |
| Gemini 3.8 Flash + Search, within the free allowance | ~$0.003 | $0.03–0.07 |
| Perplexity Agent API, `fast` preset | ~$0.003 | $0.03–0.06 |

Two fact-checking calls agreeing, as Footnote does, double the second table.
With dynamic filtering, Claude's input tokens, and so its cost, may drop
well below the 15,000-token assumption.

The free Gemini allowance of 5,000 queries a month covers about 250–500
hours of listening at 10–20 candidates an hour. That is far more than one
owner's use.

## Calling from a browser

| API | CORS preflight [probed] | Short-lived browser keys | Vendor guidance |
| --- | --- | --- | --- |
| Anthropic Messages | Allowed (`*`), including the `anthropic-dangerous-direct-browser-access` header | None for the Messages API | The TypeScript SDK blocks browsers unless `dangerouslyAllowBrowser: true`. The docs say this "exposes your secret API credentials" and is reasonable only for internal tools or development with short-lived, rotated keys [verified]. |
| OpenAI Responses | Allowed (`*`) | Only for the Realtime API (`/v1/realtime/client_secrets`) [verified] | "Only use standard OpenAI API keys on the server, not in the browser" [verified]. |
| Gemini `generateContent` | Allowed (origin echoed) | Only for the Live API ("only compatible with Live API at this time") [verified] | "Never expose keys client-side in production … run a backend proxy server" [verified]. Unrestricted standard keys are rejected, and standard keys are rejected from September 2026; auth keys are bound to a service account [verified]. |
| Perplexity | Allowed (`*`) | None found | Not stated on the pages read. |
| Groq, Cerebras | Allowed (`*`) | None found | Not stated on the pages read. |
| Exa | Answered, but no `Access-Control-Allow-Origin` in the preflight reply | None found | Unclear. |
| Tavily | Allowed (origin echoed) | None found | Not stated on the pages read. |
| TypeSafe Jev | Not probed | None documented | Not stated on the pages read. |

A browser *can* call all of these. The cost of doing so is that the key sits
in a page anyone with the URL can open, where it can be copied and used. Every
vendor points at the same fix: a small server, or a serverless function, that
holds the keys and forwards the calls. Carl's "no app install" requirement
concerns the device at the table, not where the key lives.

## Implications for Carl

Observations for the architecture and model-choice tickets. They are not
decisions.

1. **The €1/h target shapes the decision model more than anything else.**
   600 calls an hour on a Haiku-class model uses most of the budget. The
   cheap tier (Jev, GPT-6 Luna, Flash-Lite, gpt-oss) leaves room for a
   stronger fact-checking model, or for two of them agreeing. A code filter
   that drops backchannel and very short turns before any model call cuts all
   decision model estimates in proportion.
2. **A precision-first fact-checking model fits the budget at 10–20
   candidates an hour.** Even Claude Sonnet 5 with web search, run twice for
   agreement, costs about $0.9–1.8/h. That is over budget together with a
   Haiku decision model, but within it with a cheap decision model and one
   Claude call plus one cheaper second call from another vendor [estimate].
3. **Check time is the open question.** No vendor publishes a response time
   for a search-grounded answer. A timed run on recorded utterances, for each
   shortlisted fact-checking model and with one search per call, is the only
   way to know whether median ≤ 4 s is reachable.
4. **Two fact-checking calls from different vendors look like the practical
   confidence signal.** Logprobs measure token certainty, not evidence.
   Gemini's support scores are optional, and Claude has neither. Different
   vendors (for example Claude and Gemini, or Claude and Perplexity) reduce
   the "shared cultural priors" failure that Footnote saw when both of its
   arms agreed and were both wrong.
5. **Google's grounding terms clash with the test corpus.** Recording
   sessions keep full model-call logs, and the test corpus is analysed for
   precision. Google's terms forbid analysing grounded results and require
   the Search Suggestions next to them on screen. Gemini grounding may suit
   production cards, but not recording sessions, unless the terms are read
   more closely.
6. **Perplexity's product is moving under us.** Sonar ends on 2026-09-27, and
   the Agent API's `fast` preset has already switched model once. Pinning an
   explicit model and search settings is safer than relying on a preset.
7. **Finnish quality is unmeasured everywhere.** The test corpus is the only
   evidence Carl will have. That covers the decision model on Finnish
   utterances, the fact-checking model on Finnish-language sources, and the
   message-writing model's Finnish register.
8. **A key-holding server is likely.** Direct browser calls are technically
   possible to every API checked but advised against by every vendor, and no
   ephemeral keys exist for these text APIs. A small proxy is also where the
   pipeline's other server-side needs (dedupe, the failure log, the monthly
   budget tally) could live.

## Sources

Anthropic:

- Pricing: https://platform.claude.com/docs/en/about-claude/pricing
- Models overview: https://platform.claude.com/docs/en/about-claude/models/overview
- Web search tool: https://platform.claude.com/docs/en/agents-and-tools/tool-use/web-search-tool
- Tool reference: https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-reference
- Structured outputs: https://platform.claude.com/docs/en/build-with-claude/structured-outputs
- Citations: https://platform.claude.com/docs/en/build-with-claude/citations
- Prompt caching (minimum lengths): https://platform.claude.com/docs/en/build-with-claude/prompt-caching
- Multilingual support: https://platform.claude.com/docs/en/build-with-claude/multilingual-support
- TypeScript SDK (browser use): https://platform.claude.com/docs/en/cli-sdks-libraries/sdks/typescript
- Messages API reference: https://platform.claude.com/docs/en/api/messages/create

Google:

- Pricing: https://ai.google.dev/gemini-api/docs/pricing
- Models: https://ai.google.dev/gemini-api/docs/models
- Grounding with Google Search: https://ai.google.dev/gemini-api/docs/google-search
- Structured output: https://ai.google.dev/gemini-api/docs/structured-output
- API reference (`GroundingSupport`, logprobs): https://ai.google.dev/api/generate-content
- API keys: https://ai.google.dev/gemini-api/docs/api-key
- Ephemeral tokens: https://ai.google.dev/gemini-api/docs/ephemeral-tokens
- Terms (Grounding with Google Search): https://ai.google.dev/gemini-api/terms

OpenAI:

- Pricing: https://developers.openai.com/api/docs/pricing
- Models: https://developers.openai.com/api/docs/models
- Web search: https://developers.openai.com/api/docs/guides/tools-web-search
- Responses API reference: https://developers.openai.com/api/reference/resources/responses/methods/create
- Realtime over WebRTC (ephemeral keys): https://developers.openai.com/api/docs/guides/realtime-webrtc

Perplexity:

- Pricing: https://docs.perplexity.ai/docs/getting-started/pricing
- Models and the Sonar deprecation notice: https://docs.perplexity.ai/getting-started/models
- Migrating from Sonar: https://docs.perplexity.ai/docs/agent-api/migrate-from-sonar/overview
- Agent API vs Sonar benchmarks: https://docs.perplexity.ai/docs/agent-api/migrate-from-sonar/benchmarks
- Presets: https://docs.perplexity.ai/docs/agent-api/presets

Open-model hosts, search APIs and Jev:

- Groq models and prices: https://console.groq.com/docs/models
- Groq Compound deprecation: https://console.groq.com/docs/compound
- Cerebras models: https://inference-docs.cerebras.ai/models/overview
- Cerebras pricing: https://www.cerebras.ai/pricing
- Exa pricing: https://exa.ai/pricing
- Tavily credits: https://docs.tavily.com/documentation/api-credits
- TypeSafe Jev models, prices and language support: https://docs.typesafe.ai/models
- TypeSafe introduction: https://docs.typesafe.ai/introduction
