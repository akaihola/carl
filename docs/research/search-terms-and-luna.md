# Search providers' terms and Luna web search

Research for the ticket *Search providers' terms and Luna web search*
(`.scratch/first-working-carl/issues/17-search-terms-and-luna.md`), compiled
2026-09-26. It follows up
[Provisional models for each stage](../../.scratch/first-working-carl/issues/07-provisional-models.md#answer),
which picked two **fact-finding models** that run in parallel:

- **A:** GPT-6 Luna (`gpt-6-luna`) with OpenAI's hosted `web_search` tool.
- **B:** Perplexity's Agent API with the model pinned to
  `google/gemini-3.8-flash` and Perplexity's `web_search` tool.

Pricing and Google's grounding terms are already in
[models-for-text-stages.md](models-for-text-stages.md) and are not repeated.

## How this was researched, and how far to trust it

- **[verified]** marks claims read on the vendor's own documentation on
  2026-09-26. Both vendors serve their docs as Markdown (append `.md` to the
  URL), and the claims were read from that text.
- **[snippet]** marks a sentence seen only as a search-engine excerpt of the
  vendor's legal page. OpenAI's and Perplexity's legal pages
  (`openai.com/policies/*`, `perplexity.ai/hub/legal/*`) returned a
  Cloudflare challenge (HTTP 403) to every automated fetch, so **neither
  vendor's terms were read in full**. Treat every [snippet] claim, and every
  conclusion about the terms, as **unverified** until the owner reads the
  pages in a browser.
- **[inferred]** marks this note's own reading of what the docs imply.
- **No API was called.** There were no API keys, so nothing here was tested.

## 1. May Carl store, keep and analyse search results and responses?

What Carl wants to do (from `CONTEXT.md`): a **recording session** logs every
model call in full, including the fact-finding model's response and its
search results. The raw logs are deleted 6 months after recording. The
owner's corrected Markdown, which quotes draft cards and their source
excerpts, stays in the **test corpus** until the owner deletes it, and is
analysed to measure precision and recall.

### OpenAI (web search tool)

- **The web search guide sets one display rule and no storage rule.**
  "When displaying web results or information contained in web results to end
  users, inline citations must be made clearly visible and clickable in your
  user interface." [verified] Nothing in the guide limits caching, storing,
  retention time or analysis of results. There is no counterpart to Google's
  "may not cache … analyze … Grounded Results".
- **The display rule touches Carl's cards.** A fact card that shows
  information from web results must show its citation, clearly visible and
  clickable [verified]. The draft card already carries a source URL and
  title, so the card must render them as a link [inferred].
- **OpenAI's own retention** [verified, data controls guide]:
  - Abuse monitoring logs are "retained for up to 30 days" for all API use,
    and `/v1/responses Web Search` has 30 days of abuse monitoring retention.
  - "The Responses API has a 30 day Application State retention period by
    default, or when the `store` parameter is set to `true`." Carl can set
    `store: false`, since it keeps its own log.
  - "Data sent to the OpenAI API is not used to train or improve OpenAI
    models (unless you explicitly opt in)."
  - Web search with live internet access is not HIPAA-eligible. Only the
    offline, cache-only mode (`external_web_access: false`) can be covered by
    a BAA. This does not matter for Carl, but it shows live search is treated
    differently from the rest of the API.
- **The legal terms were not read.** OpenAI's statement that customers "own
  [their] inputs and outputs" was seen only as a search excerpt [snippet]. A
  search-result excerpt of the terms also says third-party services and
  output, "like [the] browse feature", are "subject to their own terms"
  [snippet]. Whether OpenAI's Service Terms put any storage or analysis limit
  on web search results is **unverified**.
- **Verdict:** nothing found forbids what Carl plans, and the docs impose only
  the visible, clickable citation. **Unverified** until the Service Terms and
  Services Agreement are read in full.

### Perplexity (Agent API)

- **Ownership:** the API terms say Perplexity "asserts no ownership rights in
  any Output" and assigns any such rights to the customer [snippet].
- **Licence scope is the open point.** The terms let a customer use the
  Services "solely to submit Input to the Service, receive Output from the
  Service, and display such Output, in each case, solely within the Customer
  Applications in accordance with the API Documentation" [snippet]. Read
  narrowly, "display … within the Customer Applications" does not obviously
  cover keeping outputs in a log and a test corpus. But Carl's recording and
  test corpus are part of Carl itself, and with the customer owning the
  Output, storing it for Carl's own testing looks allowed [inferred].
  **Unverified**: no clause on caching, retention periods or analysis was
  found in the excerpts, either allowing or forbidding it.
- **Search Services Addendum.** A separate addendum governs Perplexity's
  "Search Services". It lets Perplexity "retain, copy, distribute and
  otherwise use Search Data" for its business purposes, and says the
  zero-data-retention obligations of Perplexity's other products "do not
  apply to the Search Services" [snippet]. Its Schedule 1 lists which
  services it covers. Whether that includes the Agent API's `web_search` tool
  or only the standalone Search API is **unverified**. If it does, the search
  queries Carl sends (which are drawn from the table's conversation) may be
  kept and used by Perplexity.
- **Agent API retention** [verified]: the Agent API "persists response and
  conversation state server-side". Setting `store: false` only hides a
  response from retrieval; it "can still be used as `previous_response_id`",
  so it is still kept. The docs give no retention period. The privacy page's
  zero-data-retention promise names only the Chat Completions (Sonar) API.
- **Acceptable use:** the AUP applies to Outputs. Excerpts show bans on
  scraping the Services and on removing marks that identify output as
  AI-generated [snippet]. Nothing seen bans storing or benchmarking outputs.
- **Gemini through Perplexity:** whether Google's own Gemini API terms reach a
  customer who calls Gemini via Perplexity is not stated in the docs read
  [unverified]. It is not grounded output (Perplexity does the search), so
  Google's grounding clause should not apply [inferred, as in ticket 07].
- **Verdict:** likely allowed, with no restriction found like Google's, but
  **unverified**. The licence wording and the addendum's scope need a human
  read of the full terms.

### What this means for recording sessions

- Neither vendor's docs forbid what Google's grounding terms forbid.
- Both vendors keep their own copies: OpenAI for up to 30 days (abuse logs),
  Perplexity for an undocumented period. The 6-month deletion in a recording
  session covers only Carl's copy. The disclosure should say that the
  vendors keep request logs [inferred].

## 2. Does OpenAI's web search tool serve `gpt-6-luna`, and in which mode?

- **The model page says yes.** The `gpt-6-luna` page lists `web_search` under
  both "Supported features" and "Supported tools" for the Responses API
  [verified]. The overall models page lists web search for all three GPT-6
  models [verified].
- **The web search guide has not caught up.** Its examples use
  `gpt-6-astra`, its prose names `gpt-5.5`, and its limitations tables list
  only older models [verified]. It never mentions Luna, and it has no rule
  against Luna. The guide seems to lag the model pages, as it did for Luna
  in ticket 03 [inferred].
- **Use the Responses API.** "Use the Responses API for built-in tools and
  function calling" (Luna page) [verified]. Chat Completions web search works
  only with the special search models (`gpt-5-search-api` and older), so
  Luna there has no web search [verified].
- **Mode:** the guide describes three modes: non-reasoning search ("fast and
  ideal for quick lookups"), agentic search with reasoning models, and deep
  research [verified]. Luna is a reasoning model whose `reasoning.effort`
  takes `none`, `low`, `medium` (default), `high`, `xhigh` and `max`
  [verified]. So:
  - With `effort: "none"`, Luna should behave as non-reasoning search, the
    mode Carl wants for its time budget [inferred]. The guide warns that
    "`gpt-5.4` with reasoning effort set to `none` may produce lower-quality
    results" [verified]. It says nothing about Luna, but the same may hold.
  - With `low` or above, Luna runs agentic search, where it can also open
    pages and search within them (`open_page` and `find_in_page` are
    "supported in reasoning models") [verified].
  - The only listed ban is `gpt-5` with `minimal` reasoning [verified].
- **Search must be forced.** "With `tool_choice: \"auto\"`, search is
  optional. Use `tool_choice: \"required\"` … when search must run."
  [verified] Fact-finder A should force it.
- **Other limits** [verified]: the search context window is capped at 128k
  tokens whatever the model's window; rate limits follow Luna's tier;
  `search_context_size` (low/medium/high), `user_location`, up to 100
  allowed or blocked domains, and `external_web_access` are available on
  `web_search`.
- **Verdict:** yes on paper, in the Responses API, with non-reasoning search
  at `effort: "none"` or agentic search at `low`+. **Unverified in practice**
  (no call made). The first real call settles it. The fallback in ticket 07
  (Luna via Perplexity, `openai/gpt-6-luna`, which the Agent API lists
  [verified]) stays available.

## 3. Gemini on Perplexity, structured output, and verbatim excerpts

### Does the Agent API take a pinned `gemini-3.8-flash` with `web_search` and structured output?

- **The model is served.** `google/gemini-3.8-flash` is on the Agent API
  models page at $0.75 / $3.75 per 1M tokens, default service tier only
  [verified].
- **Pinning:** a request names one model with `model` (in `provider/model`
  form) or a fallback chain with `models` (up to 5) [verified]. The id has no
  dated snapshot, so Google or Perplexity could change what sits behind it
  [inferred]. The response reports the model that ran, which Carl should
  record.
- **`web_search`:** added in the `tools` array, and "the model decides when
  to call it" [verified]. The web search page lists no model limits. But the
  models page warns: "Not all third-party models support all features (e.g.,
  reasoning, tools). Check model documentation for specific capabilities."
  [verified] No per-model table of features exists, so Gemini 3.8 Flash with
  tools is **unverified**.
- **Structured output:** `response_format` with
  `{"type": "json_schema", "json_schema": {"name", "schema"}}`; "the response
  text conforms to the schema unless generation is cut short" [verified].
  Caveats [verified]:
  - "The first request with a new JSON Schema expects to incur delay on the
    first token. Typically, it takes 10 to 30 seconds to prepare the new
    schema, and may result in timeout errors." Carl should warm each schema
    after a deploy.
  - "Avoid asking for links inside the JSON … Pull links from the
    `citations` or `search_results` items in the response `output`
    instead."
  - Every example uses an OpenAI model. No page says whether a Google model
    honours `response_format`, or whether it combines with `web_search`.
- **Verdict:** each piece is documented, but the combination (Gemini 3.8 Flash
  + `web_search` + `response_format`) is **unverified**. Test it with one
  call before building fact-finder B on it.

### Do citations carry a verbatim excerpt for the draft card's source excerpt?

**OpenAI: no.**

- A `url_citation` annotation holds `url`, `title`, `start_index` and
  `end_index` [verified]. The indexes point into Carl's *answer text*, not
  into the source page. There is no quoted source text.
- `include: ["web_search_call.action.sources"]` returns "the complete list of
  URLs the model consulted" [verified]. The guide describes URLs, not page
  text.
- The raw search results never reach Carl, so Carl cannot check in code that
  an excerpt the model wrote actually appears in the source [inferred].
  Options: ask for the excerpt in the structured output and fetch the URL to
  check it (an extra round trip), or leave the check to the fact-checking
  model.
- Whether `url_citation` annotations still come back when the output is a
  JSON schema is **unverified**.

**Perplexity: partly.**

- Each `web_search` run adds a `search_results` output item before the
  message. Each result has `id`, `url`, `title`, `snippet`, `date`,
  `last_updated` and `source`. `snippet` is "Excerpted text extracted from
  the page during search" [verified].
- The message's `annotations` can hold `url_citation` entries with
  `start_index`, `end_index`, `url` and `title` (API reference) [verified].
  The web search page says inline markers are "prompt-dependent" and to
  "treat the `id` and `url` fields of each `search_results` entry as the
  source of truth for citations" [verified].
- So Carl gets page text, but it belongs to the search result, not to the
  sentence the model wrote. Whether a snippet is always verbatim, and how
  long it is (`search_context_size` sets a token budget of 300, 1,000 or
  4,000 tokens for all results together [verified]), is **unverified**.
- A workable check [inferred]: ask the model for a source excerpt in the
  structured output, and accept the draft card only if that excerpt is a
  substring of a `snippet` from the same URL.

## Open items for the owner

1. Read OpenAI's Service Terms and Services Agreement in a browser and search
   for "web search", "search results", "cache" and "store".
2. Read Perplexity's API Terms of Service and the Search Services Addendum,
   especially the licence clause and Schedule 1 (does it cover the Agent
   API's `web_search`?).
3. With API keys, make three calls: Luna + `web_search` at `effort: "none"`
   with a JSON schema; the same on Perplexity with `google/gemini-3.8-flash`;
   and check what citations and snippets come back.

## Sources

OpenAI:

- Web search guide: https://developers.openai.com/api/docs/guides/tools-web-search (Markdown: append `.md`)
- GPT-6 Luna model page: https://developers.openai.com/api/docs/models/gpt-6-luna
- Models overview: https://developers.openai.com/api/docs/models
- Data controls (retention, ZDR, web search): https://developers.openai.com/api/docs/guides/your-data
- Service Terms (not readable, 403): https://openai.com/policies/service-terms/
- Services Agreement (not readable, 403): https://openai.com/policies/services-agreement/
- Usage policies (not readable, 403): https://openai.com/policies/usage-policies/

Perplexity:

- Agent API quickstart: https://docs.perplexity.ai/docs/agent-api/quickstart
- Agent API models: https://docs.perplexity.ai/docs/agent-api/models
- Web search tool: https://docs.perplexity.ai/docs/agent-api/tools/web-search
- Structure the output: https://docs.perplexity.ai/docs/agent-api/building-agents/shape-output
- Output control: https://docs.perplexity.ai/docs/agent-api/output-control
- Conversation state (persistence, `store`): https://docs.perplexity.ai/docs/agent-api/conversation-state
- Privacy and security: https://docs.perplexity.ai/docs/resources/privacy-security
- API reference (create response): https://docs.perplexity.ai/api-reference/agent-post
- API Terms of Service (not readable, 403): https://www.perplexity.ai/hub/legal/perplexity-api-terms-of-service
- Search Services Addendum (not readable, 403): https://www.perplexity.ai/hub/legal/perplexity-api-terms-of-service-search
- Acceptable Use Policy (not readable, 403): https://www.perplexity.ai/hub/legal/aup
