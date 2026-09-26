# Read OpenAI's and Perplexity's legal terms

Type: task
Status: open
Blocked by:

**This is a job for the owner.** An agent can't do it: both vendors' legal
pages returned a Cloudflare challenge (HTTP 403) to every automated fetch, so
they have to be read in a browser. It is the last row of
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
5. Anything else that touches how Carl uses either API.

## Done when

- [ ] The pages above have been read.
- [ ] The answers are written under an `## Answer` heading here, quoting the
      clauses that decide each question.
- [ ] If a term forbids something the spec plans, it is raised as a decision
      before step 4 starts. This ticket doesn't choose the remedy.
