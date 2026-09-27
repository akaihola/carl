# Step 5: Second fact-finder

Type: task
Status: resolved
Blocked by: 05

Build step 5 of the [First working Carl spec](../../first-working-carl/spec.md#14-build-order).
The spec is the source of truth. This ticket lists what the step builds and
where the spec describes it. If the step is too big for one agent session,
split it into further tickets in this folder before starting.

## What to build

- **Both fact-finders in parallel** on every candidate
  ([Fact-finding](../../first-working-carl/spec.md#fact-finding)):
  - the other fact-finder's adapter, with the models step 0 chose;
  - the same prompt and the same input for both.
  - The decision call's list shows the first restatement to arrive. The
    recording keeps both.
- **Waiting for both** ([Waiting for both](../../first-working-carl/spec.md#waiting-for-both)):
  - Carl waits until about 12 s after the first outcome arrives (config);
  - a fact-finder that fails or misses the deadline leaves the other's card
    to be judged alone;
  - a card is never shown first and then confirmed or withdrawn later.
- **Fact-finder A's page download**, if step 4 didn't already build it
  ([Matching excerpts against their sources](../../first-working-carl/spec.md#matching-excerpts-against-their-sources)):
  - about 3 s timeout, then a search for the excerpt after normalising
    whitespace and quotation marks;
  - each download is recorded as a call costing 0.
- **The agreement call** ([Verdicts and the agreement call](../../first-working-carl/spec.md#verdicts-and-the-agreement-call)):
  - `prompts/same-fact.md`, starting from the step-0 draft;
  - one typed call to the fact-checking model, alongside the verdicts, when
    both fact-finders return the same outcome, given the candidate and both
    cards;
  - `same fact` means agreement, `compatible but different` means each card
    is judged alone, and `contradict` means nothing is shown;
  - `claim is wrong` against `claim is right` is a contradiction with no
    call. A card against `not found`, or against a failed fact-finder, is
    judged alone.
  - Nothing is translated.
- **The plain band and the full split** ([The bands](../../first-working-carl/spec.md#the-bands)):
  - plain: agreement with p(same fact) ≥ 0.7; the shown card has a verified
    excerpt, a source that isn't blocklisted and p(supported) ≥ 0.85; the
    other card has p(supported) ≥ 0.5;
  - hedged: one card with a verified excerpt, a source that isn't blocklisted
    and p(supported) ≥ 0.6, and no contradiction from the other fact-finder;
  - nothing otherwise, and on any contradiction;
  - the verified card is shown, or the one with the higher p(supported) if
    both are verified;
  - with no logprobs from the fact-checking model, a card is hedged at best;
  - every band is recorded with its reason code (`plain:agreed`,
    `hedged:single-verified`, `silent:contradiction`, `silent:unverified`…).
- **Cost metering** for the second fact-finder and the agreement call.
- **Recording:** both restatements, both draft cards, both verdicts with
  probabilities, the agreement call, A's download result and B's snippet
  match.
- **Example cases** for `same-fact.md` under `prompts/examples/`, in Finnish
  and English.

## Leaves working

The full split into plain, hedged and nothing.

## Done when

- [x] pytest passes in GitHub Actions on push to `main`, with fake adapters
      and no live provider calls: every band and reason code, the outcome
      pairs that skip the agreement call, which card is shown, the wait for
      the second fact-finder and excerpt normalisation.
- [x] The agreement prompt's example cases have been run by hand against the
      configured model.
- [ ] Deployed and used for one session on the phone, at a real dinner or
      with a Finnish radio talk show playing beside it.

## Answer

Built on 2026-09-27, extending ticket 32's `src/carl/checks.py`:
`prompts/same-fact.md` with its `FILLS` entry, `prompts/examples/same-fact.toml`
and `carl examples same-fact`, `Sessions.close` (called at shutdown after
every session has ended), and step 5's tests in `tests/test_checks.py` (87
tests there; the whole suite, 665, passes locally, and GitHub Actions runs it
on the push). The first two items under "Done when" are met; the phone
session is still to come.

- **Both fact-finders at once.** `Checker.finders` maps `A` and `B` to
  their adapters. Both get the same prompt and input; A's search tool gets
  `openai_user_location` and B's `perplexity_user_location`. Each runs as
  its own task, which End waits for: the finding (recorded as it arrives,
  with the seconds since the utterance), then its draft card's blocklist and
  excerpt check. The first restatement to arrive goes onto the candidate;
  the recording keeps both. The retry-once rule for a 429 applies to either.
  With one fact-finder's key alone, `install` runs with that one and warns
  that only hedged cards are possible; with neither, there are no checks.
- **Waiting for both.** Once the first part is ready, Carl waits
  `second_finder_wait_s` (12 s) for the other. One that fails or misses the
  wait leaves the other's card judged alone. A missed one finishes in the
  background, so its finding is recorded and its cost charged, but it
  changes nothing: a card is never shown and then confirmed or withdrawn. A
  `findings` event records which were used, failed or missed. If both fail,
  the candidate fails at `fact-finding`, with both errors. A's part includes
  its page download (at most 3 s), so the wait may count from a little after
  A's outcome arrived.
- **Matching excerpts** by provider: a Perplexity fact-finder's against its
  snippets, an OpenAI one's against its downloaded page (`page_match`, with
  `source_download_timeout_s` and one `download_client` per checker, closed
  at shutdown). Each download is recorded as a `download` event costing 0,
  with its status, type, final URL, time and bytes. A blocklisted source is
  never downloaded, since its card can't be shown and the other card of an
  agreeing pair needs no verified excerpt.
- **Verdicts and the agreement call** go to Jev at once. A card's verdict is
  asked only when it can change the band (`needs_verdict`): a card that
  could be shown, or either card of a pair with the same outcome if at least
  one of them could be shown, since the plain band needs the other card's
  p(supported). A contradiction or mixed outcomes show nothing, so neither
  verdict is asked. The agreement call runs whenever both cards have the same
  outcome, so every silent pair gets its true reason code. It gets the
  candidate's line, both cards as `title: fact` (A's as `card_1`) and the
  date and time; never a restatement, an excerpt or a source. Nothing is
  translated.
- **The bands** come from `checking.band_pair`. A plain card has no tag and
  no hedge prefix. The candidate fails at `fact-checking` only when a failed
  verdict or agreement call leaves nothing (`silent:no-verdict`,
  `silent:no-agreement`); a card still shown despite one failed verdict is
  just a card.
- **Costs:** `fact-finding A` (tokens plus OpenAI's search fees),
  `fact-finding B`, and `fact-checking` for verdicts and the agreement call.
- **Tests** cover every reason code through the pipeline, the outcome pairs
  that skip the agreement call, which card is shown, the wait (a second
  fact-finder within it, one that misses it and is still recorded and
  charged afterwards, a failure before the first arrival not starting it,
  one failed, both failed), A's download feeding `verified`, each tool's
  `user_location`, costs, the recording, the shutdown close, and a plain card
  through the WebSocket.
- **Agreement example cases:** 8 (3 same fact, 2 compatible, 3 contradict; 5
  Finnish or mixed), all as expected from `typesafe/jev-1.13`
  (`jev-1.13-20260917`), at 0.90–1.00, for $0.0002 in all.
  `prompts/same-fact.md` is the step-0 draft with `date_time` named.
- **One live candidate**, both fact-finders, Kallio, 2026-09-27: "Joo,
  vuonna 1956. Isä kävi katsomassa." Both said `claim is wrong` (B after
  8.3 s, A after 8.8 s, from the utterance), and the agreement call said
  `same fact` at 1.0. B's excerpt matched a snippet and Jev supported its
  card at 0.98. A's page downloaded and its excerpt was found, but the
  excerpt ("The Games anticipated an unprecedented stream of tourists…")
  doesn't state the year, and Jev said `not supported` at 0.96. So B's card
  went out hedged, `hedged:agreed-below-plain`, 11.4 s after the utterance,
  for $0.030: A $0.0219 (17,494 input tokens), B $0.0077, decision and
  four Jev calls $0.0001.
- **Seen live, for the comparison:** both facts added "the 1956 Games were
  in Melbourne", which neither excerpt states, and Jev still supported B's
  card at 0.98. The prompt's `supported` allows the excerpt to say more than
  the card, not the other way round, so this is a verdict to watch in the
  corpus.
