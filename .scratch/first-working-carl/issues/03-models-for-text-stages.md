# Models for the decision, fact-checking and message-writing stages

Type: research
Status: resolved
Blocked by: 

## Question

Which models are available now for the three text stages, and what do they cost and how fast are they? Decision model: cheap, fast, structured output, Finnish. Fact-checking model: web search or grounding with citable sources, structured verdicts, latency against a median 4 s / p90 8 s check time, and any usable confidence signal (logprobs, two verifiers agreeing as in Footnote, grounding scores). Message-writing model: short Finnish and English text in an encyclopedic register. For each, note price per call at typical sizes, so running cost can be estimated against about €1 per hour of listening, and whether it can be called from a browser. Findings go in `docs/research/models-for-text-stages.md`.

## Answer

Findings: [docs/research/models-for-text-stages.md](../../../docs/research/models-for-text-stages.md)

- **Decision model:** a Haiku-class model at ~600 utterances/h costs about $0.60/h, most of the €1/h budget. The cheap tier costs a few cents an hour: TypeSafe Jev ($0.042 per 1M input tokens, output free), GPT-6 Luna ($0.10/$0.50), Gemini Flash-Lite, and gpt-oss on Groq.
- **Fact-checking model:** the search fee dominates the cost ($2.50–$14 per 1,000). At 10–20 candidates/h it costs from a few cents an hour (Gemini within its 5,000 free queries/month, Perplexity Agent API `fast` preset) to about $0.45–0.90/h (Claude Sonnet 5 + web search).
- **Check time:** no vendor publishes a response time for search-grounded answers, so whether median ≤ 4 s is reachable must be measured on recorded utterances.
- **Confidence signal:** OpenAI and Gemini expose logprobs, Gemini has optional grounding support scores, and Claude has neither. Two fact-checking calls from different vendors agreeing, as Footnote does, remains the practical signal.
- **Perplexity Sonar ends 2026-09-27;** its successor is the Agent API. Google's grounding terms require showing Search Suggestions and forbid analysing grounded results, which conflicts with recording sessions and the test corpus.
- **Message-writing model:** the cost is negligible (under $0.04/h for any model). Finnish quality is unmeasured for every candidate: no vendor publishes Finnish scores.
- **Browser calls:** every API checked answers a CORS preflight, but every vendor advises keeping keys on a server. Ephemeral keys exist only for OpenAI's and Google's realtime and live voice APIs, not for these text APIs.
