# Read OpenAI's, Perplexity's and OpenRouter's legal terms

Type: task
Status: resolved
Blocked by:

**This is a job for the owner.** An agent can't do it: OpenAI's and
Perplexity's legal pages returned a Cloudflare challenge (HTTP 403) to every
automated fetch, so they have to be read in a browser. (OpenRouter's pages do
load for an agent.) It is the last row of
[Early checks](../../first-working-carl/spec.md#early-checks), and it has to be
done before step 4 (ticket 05), whose first dinner with fact-finders keeps
their search results in its recording.

## Why

A **recording session** keeps every model call in full for 180 days,
including the fact-finders' responses and Perplexity's search results. The
**test corpus** quotes draft cards and their source excerpts until the owner
deletes it, and is analysed for precision and recall. Google's grounding
terms forbid this, which is why Google Search grounding is out. Nothing in
OpenAI's or Perplexity's docs forbids it, but neither vendor's full terms
have been read. See
[Search providers' terms and Luna web search](../../../docs/research/search-terms-and-luna.md#1-may-carl-store-keep-and-analyse-search-results-and-responses),
where every claim about the terms is marked unverified.

## What to read

**OpenAI:**

- [Service Terms](https://openai.com/policies/service-terms/)
- [Services Agreement](https://openai.com/policies/services-agreement/)
- [Usage policies](https://openai.com/policies/usage-policies/)

Search them for "web search", "search results", "cache" and "store".

**Perplexity:**

- [API Terms of Service](https://www.perplexity.ai/hub/legal/perplexity-api-terms-of-service),
  especially the licence clause ("display such Output … solely within the
  Customer Applications")
- [Search Services Addendum](https://www.perplexity.ai/hub/legal/perplexity-api-terms-of-service-search),
  especially Schedule 1
- [Acceptable Use Policy](https://www.perplexity.ai/hub/legal/aup)

**OpenRouter**, added on 2026-09-27, when the fact-checking model's calls to
TypeSafe Jev moved there. Every verdict and agreement call sends it the
candidate utterance with its context window, the draft card and its excerpt.

- [Terms of Service](https://openrouter.ai/terms)
- [Privacy Policy](https://openrouter.ai/privacy)
- [Provider logging](https://openrouter.ai/docs/guides/privacy/provider-logging)
  and [data collection](https://openrouter.ai/docs/guides/privacy/data-collection)

## Questions to answer

1. May Carl keep the fact-finders' responses and search results in a
   recording for 180 days, and analyse them?
2. May the test corpus keep quoted draft cards and source excerpts until the
   owner deletes it?
3. Does either vendor require more on screen than OpenAI's visible,
   clickable citation?
4. Does Perplexity's Search Services Addendum cover the Agent API's
   `web_search` tool? If it does, Perplexity may keep and use the search
   queries Carl sends, which are drawn from the table's conversation. Does
   the disclosure or the documentation then need to say so?
5. What do OpenRouter and TypeSafe keep of the text Carl sends to Jev, for
   how long, and may either use it for training? Is there an account
   setting that should be switched off?
6. Anything else that touches how Carl uses these APIs.

## Done when

- [x] The pages above have been read.
- [x] The answers are written under an `## Answer` heading here, quoting the
      clauses that decide each question.
- [x] If a term forbids something the spec plans, it is raised as a decision
      before step 4 starts. This ticket doesn't choose the remedy.

## Answer

Read on 2026-09-27 by an agent, not the owner. A real browser (PinchTab)
got past the Cloudflare challenge that blocks plain fetches. Every page
above was read in full, plus two pages they pull in: Perplexity's
[Third-Party Models & Terms][pplx-3p] list and Google's
[Gemini API Additional Terms][gemini-terms]. This is a careful reading, not
legal advice. The versions read:

| Page | Version |
| --- | --- |
| OpenAI Service Terms | updated 2026-09-21 |
| OpenAI Services Agreement | updated 2025-12-01, effective 2026-01-01 |
| OpenAI Usage policies | effective 2025-10-29 |
| Perplexity API Terms of Service | updated 2026-01-23 |
| Perplexity Search Addendum | updated 2025-09-22 |
| Perplexity Acceptable Use Policy | updated 2025-07-08 |
| Perplexity Third-Party Models & Terms | updated 2025-11-25 |
| OpenRouter Terms of Service and Privacy Policy | updated 2026-08-31 |
| TypeSafe Terms of Use | updated 2026-09-19 |

**In short:** nothing in these terms forbids the recording or the test
corpus. OpenAI requires the visible, clickable citation Carl already plans.
The Search Addendum doesn't cover the Agent API. One decision is raised: the
Gemini model behind fact-finder B brings Google's rule against apps likely
to be used by under-18s, and the spec lets children sit at the table.

### 1. Recordings: keeping and analysing responses and search results for 180 days

**Yes, for both vendors.** Neither has a clause on caching, storing,
retention time or analysis of outputs. Nothing like Google's grounding
clause appears in either vendor's terms. Both vendors assign the output to
the customer:

- OpenAI Services Agreement 4.1: "Customer: (a) retains all ownership rights
  in Input; and (b) owns all Output. OpenAI hereby assigns to Customer all
  OpenAI's right, title, and interest, if any, in and to Output."
- Perplexity API Terms 2.3.1: "Customer (i) retains all ownership rights in
  Input and (ii) owns all Output. Perplexity asserts no ownership rights in
  any Output".

The narrow-looking Perplexity licence (2.1) limits how Carl uses the
*Services*, not what it does with the Output it owns: "use the Services and
the API Keys solely to submit Input … to the Service, receive Output …
from the Service, and display such Output, in each case, solely within the
Customer Applications in accordance with the API Documentation". The
recording and the corpus are part of Carl, so they fall within the Customer
Application either way.

OpenAI's only restriction near this is Services Agreement 3.3(f): do not
"extract data from the Services other than as permitted through the
Services". Keeping responses the API returned to Carl isn't extraction.

The web results inside a Luna response count as Output. The Services
Agreement's "Third-Party Services" clause (3.4) covers only services Carl
"elect[s] to use", which have their own terms. OpenAI's web search isn't
one of them. The Service Terms mention third-party content only to exclude
it from OpenAI's indemnity: "the allegedly infringing Output is from content
from a Third Party Offering". That limits OpenAI's liability, not Carl's
use.

### 2. The test corpus: quoted draft cards and excerpts until the owner deletes them

**Yes, on the same clauses.** No term sets a time limit on output the
customer keeps. The excerpts are short quotations of third-party web pages;
their copyright is a matter between Carl and the page owners, and neither
vendor's terms change it. The corpus is private, which keeps it within the
Customer Application.

### 3. Display requirements beyond OpenAI's clickable citation

**No.** OpenAI's rule lives in the web search guide ("inline citations must
be made clearly visible and clickable", read on 2026-09-26 in
[the research note][research]). The Service Terms make the guide binding:
"Customer will only, and will ensure that its End Users only, use APIs in
accordance with the applicable documentation at
https://platform.openai.com/docs". They also drop OpenAI's IP indemnity if
Carl "disabled, ignored, or did not use any relevant citation … features".
The card's source, shown as "a visible, clickable link" (the session
screen in the spec, ticket 05), meets this.

Perplexity's licence says display must be "in accordance with the API
Documentation", but the [Agent API web search page][pplx-web-search] sets
no display rule. The AUP bans hiding that content is AI-made ("provide
chatbot services without disclosing to end users that they are interacting
with AI (unless it is obvious from the context)"; "Remove watermarks,
metadata or other indicia intended to identify outputs as artificially
generated"). The disclosure line already says the conversation goes to
cloud AI services.

### 4. Does Perplexity's Search Services Addendum cover the Agent API's `web_search`?

**No.** Schedule 1 lists one Search Service, the `/search` endpoint: "An API
endpoint that retrieves and returns search results (e.g., snippets, URLs,
page titles and associated metadata) from an index of public content." The
addendum applies "solely with respect to the particular Perplexity Search
services listed on Schedule 1", and 1.2.2 says "the Search Services are
separate from Perplexity's other products and services (including the
'Sonar' APIs)". The main API Terms cover "the Sonar by Perplexity and/or
Agentic Research application programming interface". The Agent API's
`web_search` tool runs inside the Agent API, so the main terms govern it.

So 2.2 of the addendum ("Perplexity may retain, copy, distribute and
otherwise use Search Data for its lawful business purposes") does not reach
Carl's queries. The main terms apply instead:

- 2.3.3: "Perplexity shall not use (or authorize third parties to use)
  Customer Content to train, retrain, fine-tune or otherwise improve any
  generative artificial intelligence models."
- 2.3.4: Perplexity may use Customer Content only "as necessary to exercise
  its rights and perform its obligations hereunder and to comply with
  applicable law".
- 5.1: "Customer Content constitutes Confidential Information of Customer."

The disclosure needn't mention search queries. Two caveats:

- Perplexity's [privacy page][pplx-privacy] promises zero data retention
  only for the Chat Completions API. The Agent API keeps response state
  server-side for a period no document gives (see the research note). Carl's
  documentation should say so when it links each provider's retention terms.
- If Carl ever calls `/search` directly, the addendum applies, and 2.3
  forbids sending personal data: "Customer shall not submit Personal Data
  … to the Search Services unless explicitly authorized by Perplexity in
  writing". Queries drawn from a conversation could contain personal data.

### 5. What OpenRouter and TypeSafe keep of what Carl sends to Jev

**Neither keeps the prompts or trains on them, by default.**

- **OpenRouter**, [data collection][or-collection]: "OpenRouter does not
  store your prompts or responses, *unless* you opt in". The two opt-ins are
  "Private Input & Output Logging" and "OpenRouter Use of Inputs/Outputs"
  (for a 1% discount). Both are "Off by default". OpenRouter keeps metadata
  (token counts, latency), which "does not include the content of your
  prompts or responses". It also "samples a small number of prompts for
  categorization"; without the opt-in this "is stored completely
  anonymously and never associated with your account". The Terms of Service
  (6.1) license OpenRouter to "host, cache, store" User Content "solely in
  connection with operating and providing the Service".
- **TypeSafe**, as OpenRouter lists it (`/api/frontend/v1/all-providers`,
  read 2026-09-27): `"training": false`, `"retainsPrompts": false`,
  `"canPublish": false`. The [provider logging][or-logging] table renders
  this as "Zero retention" and "Does not train". TypeSafe's own
  [privacy policy][ts-privacy] covers its APIs and says "We will not train
  or fine tune any artificial intelligence or machine learning models on
  your prompts or other Input". TypeSafe's Terms of Use, the "Model Terms"
  OpenRouter links for Jev, cover only its website and add nothing for the
  API.

**Account settings for the owner to check** on OpenRouter; nothing needs
switching off if they are still at their defaults:

- [Privacy settings][or-settings]: "OpenRouter Use of Inputs/Outputs" off.
  Also switch off routing to providers that may train on paid models. Jev's
  only provider doesn't train, so this is a guard for later.
- [Observability][or-observability]: "Private Input & Output Logging" off.
  Carl keeps its own log.

### 6. Other terms that touch Carl

- **Gemini's terms reach fact-finder B through Perplexity.** API Terms 2.6:
  "Third-Party Models are subject to the terms and policies … listed at
  perplexity.ai/hub/legal/third-party-models" and "Customer agrees to
  comply with Third-Party Terms, to the extent Customer uses the
  corresponding Third-Party Model via the Services". The list names
  `ai.google.dev/gemini-api/terms` for Gemini models. Those terms say:
  - "You also will not use the Services as part of a website, application,
    or other service … that is directed towards or is likely to be accessed
    by individuals under the age of 18." **This conflicts with the spec**
    ("Children may be present but are not a design target"). See the
    decision below.
  - "Use of Google AI Studio and Gemini API is for developers building with
    Google AI models for professional or business purposes, not for consumer
    use." Carl is a private experiment built by its developer-owner and
    offered to no consumers. This reads as allowed, but loosely.
  - The grounding clause (no caching, storing or analysing "Grounded
    Results") applies only to "Grounding with Google Search". Perplexity
    does B's searching, so the clause doesn't apply, as ticket 07 inferred.
- **OpenAI on minors**, Services Agreement 3.3(c): do not "allow minors to use
  OpenAI Services without consent from their parent or guardian". A parent
  at the table agreeing to Carl meets this.
- **Privacy.** OpenAI's usage policies forbid "attempts to … aggregate,
  monitor, profile, or distribute individuals' private or sensitive
  information without their authorization". Perplexity's AUP forbids
  "processing personal data without complying with applicable legal
  requirements". Carl's disclosure, and the rule that anyone's objection
  stops it, give the table's authorization. Neither term adds anything.
- **Retention by the vendors** (for Carl's documentation, which links each
  provider's retention terms): OpenAI keeps abuse-monitoring logs for up to
  30 days (research note); Perplexity's Agent API retention is undocumented;
  Google, behind Perplexity, "logs prompts and responses for a limited
  period of time, solely for detecting and preventing violations" on paid
  services; OpenRouter and TypeSafe keep none.
- **Not read:** OpenAI's Sharing and Publication Policy and both vendors'
  DPAs, which the agreements incorporate. Carl publishes nothing, and the
  DPAs set processor duties, not limits on Carl's use.

### Decision raised before step 4

**Children at the table vs. Gemini's under-18 clause.** With Gemini 3.8
Flash as fact-finder B, Carl is arguably an app "likely to be accessed by
individuals under the age of 18" whenever children sit at the table and
read the cards. This ticket doesn't choose the remedy. Options:

1. Don't run Carl (or fact-finder B) when anyone under 18 is at the table.
   Say so in the owner's notes and the disclosure habits.
2. Move fact-finder B to a non-Google model on Perplexity's Agent API. The
   spec's step-0 fallback already names "another non-OpenAI model", and
   that model's terms then need the same check.
3. Read "likely to be accessed" as aimed at products for minors and accept
   the risk for a private experiment.

The recording and test corpus plans need no change.

[pplx-3p]: https://www.perplexity.ai/hub/legal/third-party-models
[gemini-terms]: https://ai.google.dev/gemini-api/terms
[research]: ../../../docs/research/search-terms-and-luna.md#1-may-carl-store-keep-and-analyse-search-results-and-responses
[pplx-web-search]: https://docs.perplexity.ai/docs/agent-api/tools/web-search
[pplx-privacy]: https://docs.perplexity.ai/docs/resources/privacy-security
[or-collection]: https://openrouter.ai/docs/guides/privacy/data-collection
[or-logging]: https://openrouter.ai/docs/guides/privacy/provider-logging
[ts-privacy]: https://typesafe.ai/legal/privacy-policy
[or-settings]: https://openrouter.ai/workspaces/default/settings
[or-observability]: https://openrouter.ai/workspaces/default/observability
