# Step 4: First cards

Type: task
Status: open
Blocked by: 04, 11, 30, 31, 32, 33

Build step 4 of the [First working Carl spec](../../first-working-carl/spec.md#14-build-order).
The spec is the source of truth. This ticket lists what the step builds and
where the spec describes it. This step is probably too big for one agent
session. Split it into further tickets in this folder before starting.

Ticket 11 (the owner reads OpenAI's and Perplexity's legal terms) blocks this
step: the first dinner with fact-finders keeps their search results in its
recording.

## What to build

- **One fact-finder:** fact-finder B, or fact-finder A if B failed the step-0
  smoke test ([Fact-finding](../../first-working-carl/spec.md#fact-finding)).
  - The fact-finding adapter behind the provider-neutral interface
    ([Stage interfaces](../../first-working-carl/spec.md#stage-interfaces)):
    - input: the candidate, its context, the date, time and place, and the
      card language;
    - output: an outcome (`claim is wrong / claim is right / question
      answered / not found`), the standalone restatement, and for `claim is
      wrong` and `question answered` a draft card (title, one-sentence fact,
      source URL and title, verbatim excerpt).
  - `prompts/fact-finding.md`, starting from the step-0 draft. It asks for
    primary or reference sources and never forums, social media or video.
  - The search tool gets `user_location` as place names, never coordinates.
  - The restatement replaces the raw utterance in the decision call's list of
    earlier candidates.
- **Excerpt matching** for that fact-finder
  ([Matching excerpts against their sources](../../first-working-carl/spec.md#matching-excerpts-against-their-sources)):
  - B's excerpt must be a substring of a `search_results` snippet from the
    same URL;
  - A's source URL is downloaded (about 3 s timeout) and the excerpt looked
    for after normalising whitespace and quotation marks.
  - A match makes a **verified excerpt**. A miss or a failed download isn't a
    failure-log entry.
- **The blocklist** ([The blocklist](../../first-working-carl/spec.md#the-blocklist)):
  - domain suffixes in the config file, checked on the source URL after the
    fact-finder returns;
  - never put in a prompt.
- **Fact-checking verdicts** ([Verdicts and the agreement call](../../first-working-carl/spec.md#verdicts-and-the-agreement-call)):
  - the fact-checking model that step 0 confirmed, through the typed-answer
    interface;
  - `supported / not supported / doesn't answer the candidate`;
  - given the candidate utterance with its context window, the draft card,
    its excerpt, and the date and time, but never the restatement;
  - `prompts/fact-checking.md`, starting from the step-0 draft.
- **Hedged cards only** ([The bands](../../first-working-carl/spec.md#the-bands),
  [The hedge](../../first-working-carl/spec.md#the-hedge)):
  - a hedged fact card needs a verified excerpt, a source that isn't
    blocklisted, and p(supported) ≥ 0.6;
  - with no logprobs, `supported` meets the hedged threshold;
  - everything else shows nothing;
  - Carl adds the hedge prefix ("Todennäköisesti:" / "Probably:"), the
    Claim/Question label (Väite / Claim, Kysymys / Question) and the
    "Varauksin" / "Hedged" tag, in the card language;
  - each band is recorded with its reason code.
- **The candidate's own task** ([Candidates run side by side](../../first-working-carl/spec.md#candidates-run-side-by-side)):
  - no queue;
  - states finding → checking → ready → on screen, card history, silent or
    failed.
- **The session screen** ([The session screen](../../first-working-carl/spec.md#the-session-screen)):
  - portrait and landscape, dark, readable at 0.5–2 m;
  - the current card: the label, the hedged tag, the title, the fact, and the
    source as a visible, clickable link. The link opens in a new tab and
    leaves the card. A tap anywhere else moves on.
  - the card history: a right-hand column about 30% wide in landscape, a
    bottom strip about 30% high in portrait. Rows are newest first by
    utterance time, with ≠ for a claim, ? for a question, a dashed edge for
    a hedged card, and a link to the source.
  - the [screen prototype](../../first-working-carl/prototypes/the-screen/screen-prototype.html)
    shows the chosen layouts (P and L1, round 2).
- **Pacing and late cards** ([Pacing and late cards](../../first-working-carl/spec.md#pacing-and-late-cards)):
  - with no other card waiting, a card stays until someone taps it away;
  - with another card waiting, it stays at least 8 s, with "+N waiting" and
    a shrinking 8 s bar;
  - waiting cards are shown in utterance order;
  - a card that can't reach the screen within 20 s of its utterance goes
    straight into the card history;
  - the server sends each card with its utterance time, and the page reports
    when each card was shown or filed.
- **Cost metering** for fact-finding (tokens and search fees) and
  fact-checking. Perplexity's own cost figure counts toward the totals, and
  the difference is logged ([Cost metering](../../first-working-carl/spec.md#11-cost-metering)).
- **The "Session ended" summary** now shows its card count.
- **Recording**, for each candidate: the restatement, the draft card, the
  verdict with probabilities, the snippet match or download result, any
  blocklist match, the band with its reason code, the card language, the
  languages of the card and the excerpt; and every card sent, shown and
  filed, with the times the page reported.
- **Example cases** for `fact-finding.md` and `fact-checking.md` under
  `prompts/examples/`, in Finnish and English.

## Leaves working

Cards live at the table.

## Done when

- [x] pytest passes in GitHub Actions on push to `main`, with fake adapters
      and no live provider calls: the hedged band, the blocklist's suffix
      matching, excerpt matching, the late-card cut-off and the fact-finding
      and fact-checking cost maths.
- [x] The new prompts' example cases have been run by hand against the
      configured models.
- [ ] Deployed and used for one session on the phone, at a real dinner or
      with a Finnish radio talk show playing beside it, with cards shown
      live.

## Comments

- 2026-09-27: Split into sub-tickets: [30](30-step-4-fact-finders.md) the
  fact-finding adapters (A and B, since step 5 needs A), [31](31-step-4-checking.md)
  excerpts, blocklist, bands and card wording, [32](32-step-4-candidate-checks.md)
  a candidate's check from finding to card, and
  [33](33-step-4-cards-on-the-page.md) cards on the page. The code is built
  ahead of ticket 11; fact-finding isn't deployed until the owner has read
  the terms.
- 2026-09-27: [Ticket 11](11-read-openai-and-perplexity-terms.md#answer) is
  resolved: the terms allow the recording and the test corpus. Gemini's
  terms, which reach fact-finder B through Perplexity, bar apps "likely to be
  accessed by individuals under the age of 18". The owner ruled that
  children who overhear the table are not users of Carl, so nothing blocks
  deploying fact-finding.
- 2026-09-27: Sub-tickets 30–33 are resolved, CI passes on every push, and
  the step is deployed on `faktat.vempai.men` (image `558c6b7`, with every
  later step's code). The example cases ran by hand: fact-finding 6 of 6
  ([ticket 30](30-step-4-fact-finders.md)) and fact-checking 8 of 8
  ([ticket 32](32-step-4-candidate-checks.md)). What's left is the owner's
  phone session with cards shown live.
