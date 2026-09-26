# Search providers' terms and Luna web search

Type: research
Status: resolved
Blocked by: 

## Question

For the fact-finding models chosen in [Provisional models for each stage](07-provisional-models.md#answer):

1. Do OpenAI's web search terms and Perplexity's Agent API terms allow Carl to
   store search results and model responses in recording sessions, keep them
   up to 6 months, and analyse them for the test corpus? (Google's grounding
   terms forbid exactly this.)
2. Does OpenAI's web search tool serve `gpt-6-luna`, and in which mode?
3. Does the Perplexity Agent API accept a pinned `gemini-3.8-flash` with
   `web_search` and structured output, and do OpenAI and Perplexity citations
   carry a verbatim excerpt usable as a draft card's source excerpt?

## Answer

Findings: [docs/research/search-terms-and-luna.md](../../../docs/research/search-terms-and-luna.md).

- **Terms (question 1): likely allowed, but unverified.** Neither OpenAI's nor Perplexity's docs forbid storing, keeping or analysing results, unlike Google. OpenAI only requires citations shown to users to be "clearly visible and clickable", so fact cards must show their source as a link. The full legal pages of both vendors blocked automated reading, so the owner should read them in a browser. Open points: Perplexity's licence wording ("display … within the Customer Applications") and whether its Search Services Addendum, which lets Perplexity keep search data, covers the Agent API's `web_search`.
- **Vendor copies:** OpenAI keeps abuse logs up to 30 days, and Carl should send `store: false`. Perplexity's Agent API keeps responses server-side even with `store: false`, for an undocumented period. The recording-session disclosure should mention vendor logs.
- **Luna + OpenAI web search (question 2): yes on paper.** The `gpt-6-luna` model page lists `web_search` for the Responses API. The web search guide still doesn't mention Luna. Reasoning effort `none` should give fast non-reasoning search, and `low` or above gives agentic search. Use `tool_choice: "required"`. Untested.
- **Gemini on Perplexity (question 3): each piece is documented, the combination is not.** `google/gemini-3.8-flash` is served, and `web_search` and `response_format` json_schema both exist. But Perplexity warns that not all third-party models support tools, and every structured-output example uses an OpenAI model. One test call is needed. New schemas can take 10–30 s on first use.
- **Verbatim excerpts:** OpenAI's `url_citation` has only a URL, a title and indexes into Carl's own answer, with no source text, so Carl can't check an excerpt in code without fetching the page. Perplexity's `search_results` carry a `snippet` ("excerpted text extracted from the page"), so Carl can accept a draft card only if its excerpt is a substring of a snippet from the same URL.
