# Step 8: Corpus and costs

Type: task
Status: open
Blocked by: 08

Build step 8 of the [First working Carl spec](../../first-working-carl/spec.md#14-build-order).
The spec is the source of truth. This ticket lists what the step builds and
where the spec describes it. If the step is too big for one agent session,
split it into further tickets in this folder before starting.

## What to build

- **The owner script's corpus commands** ([The owner-only script](../../first-working-carl/spec.md#the-owner-only-script),
  [Correcting it](../../first-working-carl/spec.md#correcting-it)):
  - `generate <id>` writes `corpus/<id>.md` as a pure function of the
    recording's event log. It refuses to overwrite a file whose status isn't
    `not started`.
  - `fetch <id>` downloads `corpus/<id>.md`.
  - `put <file>` runs `check`, then uploads over `corpus/<id>.md`.
  - `check` rejects unknown mark values; changed or missing candidate ids,
    utterance times or speaker labels; and `same_speaker` labels that don't
    exist. With `status: done`, it also requires a mark on every candidate
    and repeat block.
  - month totals: prints the month's totals per provider from `costs/`, to
    compare with the providers' dashboards.
- **The corpus Markdown format** ([The test corpus Markdown](../../first-working-carl/spec.md#the-test-corpus-markdown)),
  as in the [variant C prototype](../../first-working-carl/prototypes/recording-markdown/variant-c-blocks.md):
  - a `yaml carl-session` header: the session id; the place or places, never
    coordinates; the listening time; the config file and its hash; the cost;
    the correction `status`; the `same_speaker` pairs; the format version;
  - transcript lines such as `**A2** · 00:04:31 · text`, counted from Start,
    with small talk, skipped backchannel and the "paused" and "gap" markers;
  - a `yaml carl-candidate` block after each candidate's utterance, with the
    id, kind, shown (`plain`, `hedged` or `no`), late, check time, card text
    and source, both restatements and the verdict summary with its reason
    code;
  - `repeat_of: Cn` and its probability in a repeat's block;
  - `mark` and `note` owner fields, with the allowed values for shown cards,
    silent candidates and repeats;
  - owner-added `yaml carl-missed` blocks (`kind`, `should_say`).
  - The corpus Markdown never goes into the repo.
- **Run `generate` over every dinner recorded so far.** A recording made
  before a stage existed has fewer blocks.
- **The per-session cost summary** in `costs/`: start, duration, and cost per
  stage split into actual and estimated
  ([Cost metering](../../first-working-carl/spec.md#11-cost-metering)).
- **The Start screen's last-session line:** date, length, cost and €/h.

## Done when

- [ ] pytest passes in GitHub Actions on push to `main`, with fake adapters
      and no live provider calls: `generate` on fixture event logs (a normal
      session, a repeat, a late card, a stopped recording, a gap), every
      `check` rule, and the cost summary maths.
- [ ] Every recording made so far has a generated `corpus/<id>.md`, and one
      has been corrected by the owner and put back through `check`.
- [ ] Deployed and used for one session on the phone, at a real dinner or
      with a Finnish radio talk show playing beside it, and its cost summary
      and last-session line are shown.
