# Step 5: Second fact-finder

Type: task
Status: open
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

- [ ] pytest passes in GitHub Actions on push to `main`, with fake adapters
      and no live provider calls: every band and reason code, the outcome
      pairs that skip the agreement call, which card is shown, the wait for
      the second fact-finder and excerpt normalisation.
- [ ] The agreement prompt's example cases have been run by hand against the
      configured model.
- [ ] Deployed and used for one session on the phone, at a real dinner or
      with a Finnish radio talk show playing beside it.
