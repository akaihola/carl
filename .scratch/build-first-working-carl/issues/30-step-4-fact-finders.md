# Step 4: The fact-finding adapters

Type: task
Status: resolved
Blocked by: 27

Part of [step 4](05-step-4-first-cards.md). The
[First working Carl spec](../../first-working-carl/spec.md#stage-interfaces) is the source of truth.

## What to build

- The provider-neutral fact-finding interface: the candidate, its context,
  the date, time and place, and the card language in; an outcome, the
  standalone restatement and, for `claim is wrong` and `question answered`,
  a draft card (title, one-sentence fact, source URL and title, verbatim
  excerpt) out, with the search results and a call record.
- Fact-finder B: `google/gemini-3.8-flash` on Perplexity's Agent API with its
  `web_search` and a JSON schema. Fact-finder A: GPT-6 Luna with OpenAI's
  `web_search` on the Responses API. Both from the step-0 smoke test.
- Each search tool gets `user_location` as place names, never coordinates.
- Cost: tokens and search fees; Perplexity's own figure counts, and the
  difference is logged.
- `prompts/fact-finding.md` from the step-0 draft, and its example cases.

## Done when

- [x] pytest covers both adapters against fake servers.
- [x] The example cases have been run by hand against both.

## Answer

Built on 2026-09-27: `src/carl/finding.py`, `prompts/fact-finding.md` (the
step-0 draft unchanged, so still version e128c280) with its `FILLS` entry,
`prompts/examples/fact-finding.toml` (7 cases, 4 of them Finnish),
`carl examples fact-finding` in `src/carl/examples.py`, and
`tests/test_finding.py`: 72 tests against fake OpenAI and Perplexity servers
on localhost. Both items under "Done when" are met.

- **The interface** (`carl.finding`): a `FindingRequest` holds the prompt,
  the candidate's kind (`claim`, `open question`) and line, the context
  window's lines, `place_and_time`, the card language by name
  (`language_name("fi")` is Finnish), and each search tool's
  `user_location` as `Locator.openai_user_location(session)` and
  `perplexity_user_location(session)` give them. `FactFinder.find(request,
  stage=STAGE_A or STAGE_B)` returns a `Finding`: the outcome, the
  restatement, a `DraftCard` (title, fact, source URL and title, excerpt)
  for `claim is wrong` and `question answered` only, the `SearchResult`s
  (URL, title, snippet), the queries, the searches charged, the model the
  provider reports, `model_differs` when that isn't the pinned one, and the
  `CallRecord`. `make_fact_finder(stage, config, secrets, session)` picks
  the adapter by provider (`openai`, `perplexity`); calls time out after
  30 s by default. `request.event()` and `finding.event()` give the
  recording the prompt's name, version and values, the place each search
  tool was told, and the finding without its record.
- **Fact-finder A** (`OpenAIFinder`): the Responses API with `web_search`,
  `user_location` `{type: approximate, city, region, country, timezone}`,
  `tool_choice` `required` (the default), reasoning effort from the stage,
  a strict JSON schema, `include: ["web_search_call.action.sources"]` and
  `store: false`. Its results are the search calls' sources: URLs, a title
  when given, no snippet.
- **Fact-finder B** (`PerplexityFinder`): the Agent API with the pinned
  model, `web_search` with `search_type`, `search_context_size` and
  `user_location` `{country, region, city}`, a strict JSON schema,
  `max_steps`, `max_output_tokens`, reasoning effort and `store: false`.
  Its results are the `search_results` items with their snippets.
- **No coordinates:** each tool's `user_location` keeps only the keys
  above, so coordinates can't reach a provider even if a caller passes
  them.
- **A card is complete or it is bad output:** for `claim is wrong` and
  `question answered`, all five fields must be filled in and the source an
  `http(s)` address. The card fields of `claim is right` and `not found`
  are ignored. A missing restatement, an unknown outcome or JSON that isn't
  an object is bad output too.
- **Cost:** tokens at the price table's rates plus the searches charged at
  the stage's `search` price. For A that is each `web_search_call` of type
  `search`; for B, `usage.tool_calls_details.search_web.invocation`.
  Perplexity's `usage.cost.total_cost` goes in `provider_cost_usd` and so
  counts toward the totals; a difference of $0.000001 or more is logged. A
  call with no usage is estimated as in step 3, plus one typical search (A
  and B alike), or the searches the output shows; a request refused with a
  4xx, a 429 included, is charged no search.
- **Errors** follow `carl.models.calls`: `timeout`; `unavailable` for
  transport errors, 5xx, other 4xx and a run with status `failed`;
  `rate-limited` for 429; `bad output` for an unfinished run, a refusal,
  output that can't be read, bad JSON or an incomplete card. A bad output
  that came with usage costs its real usage.

**Live run, 2026-09-27,** Kallio, Helsinki, three cases. It cost about
$0.057, and Perplexity's figure matched Carl's to the cent every time.

| Case | Finder | Outcome | Fact | Source | In results | Time | Cost |
| --- | --- | --- | --- | --- | --- | --- | --- |
| fi-wrong-year | A | claim is wrong | Helsinki isännöi kesäolympialaiset vuonna 1952, ei vuonna 1956. | historia.hel.fi | yes | 6.9 s | $0.01169 |
| fi-wrong-year | B | claim is wrong | Helsingin kesäolympialaiset järjestettiin vuonna 1952. | fi.wikipedia.org | yes | 5.7 s | $0.00813 |
| en-open-question | A | question answered | Humphrey Bogart played Rick Blaine in Casablanca. | bfi.org.uk | yes | 3.7 s | $0.01062 |
| en-open-question | B | question answered | Rick Blaine was played by Humphrey Bogart in Casablanca. | en.wikipedia.org | yes | 4.2 s | $0.00744 |
| fi-right | A | claim is right | – | – | – | 4.2 s | $0.01060 |
| fi-right | B | claim is right | – | – | – | 5.7 s | $0.00879 |

- All six came out as expected, with the cards in the card language and
  the providers reporting `gpt-6-luna` and `google/gemini-3.8-flash`
  exactly. A's `fi-right` restatement put the 110th anniversary in 2027,
  so the date reaches the prompt.
- **Perplexity refused requests sent at once.** The first try sent all
  three cases to both fact-finders together, and Perplexity answered two
  of its three with 429. The runner now takes one case at a time, both
  fact-finders in parallel, as for one candidate. Two candidates in the
  same moment may meet this limit in a session; B then fails
  `rate-limited` and A's card is judged alone.
- **B makes one search, not two:** each call was charged one `search_web`
  invocation that ran two queries. Step 0's "two searches" were queries.
- A's Finnish excerpt for `fi-wrong-year` backs the year only
  indirectly ("… kisojen avajaispäivänä 19.7.1952"). Judging that is the
  verdict's job.
- Tokens: A 9,177–15,615 in and 123–257 out, B 5,767–7,038 in and 163–270
  out. The estimates assume 300 out.
