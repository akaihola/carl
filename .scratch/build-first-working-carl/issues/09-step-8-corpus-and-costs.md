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

- [x] pytest passes in GitHub Actions on push to `main`, with fake adapters
      and no live provider calls: `generate` on fixture event logs (a normal
      session, a repeat, a late card, a stopped recording, a gap), every
      `check` rule, and the cost summary maths.
      *(`tests/test_corpus.py` and `tests/test_cost_summary.py`.)*
- [ ] Every recording made so far has a generated `corpus/<id>.md`, and one
      has been corrected by the owner and put back through `check`.
      *(For the owner: `carl owner generate --all`, then `fetch`, correct,
      `put`.)*
- [ ] Deployed and used for one session on the phone, at a real dinner or
      with a Finnish radio talk show playing beside it, and its cost summary
      and last-session line are shown.

## Answer

Built on 2026-09-27: the corpus Markdown, `check`, the owner script's
`generate`, `fetch`, `check`, `put` and `month`, and on the server the
per-session cost summary and the last-session line for the Start screen
(see "The cost summary" below; the page shows the line). **Still for the
owner:** running `generate` over the recorded dinners and correcting one,
and the phone session.

**`src/carl/corpus.py`**, with tests in `tests/test_corpus.py`:

- `generate(events)` is a pure function of the event log (every part's
  events in order), in the shape of the variant C prototype:
  - a `yaml carl-session` header: `session`, `place` (a list, each place
    as neighbourhood and town, in order; the same town with and without its
    neighbourhood is one place; a comment says why it is empty: location
    off, denied or no place known), `listening` (`1h46m`), `config`
    (`config.toml@<hash>`), `cost_usd`, `status: not started`,
    `same_speaker: []` and `format: 1`. It never reads the fix or geocoder
    events, so no coordinates or street names get in. A log with no end
    event gets the listening time counted from it and an empty cost, each
    with a comment;
  - transcript lines `**A2** · 00:04:31 · text`, time from Start to the
    first word, labels as the decision call gives them (stream letter and
    speaker). Soniox times words by the audio its stream got, so after a
    dropped page connection (the stream stays open without audio) the
    stream's clock is set right from `page gone`/`page back`, less the
    finalise silence. Markers: `*— paused 00:21:10–00:27:30 —*` from
    `pause` to `resume`, and `*— gap … —*` from `stt failed` to the next
    `stt open` and from `page gone` to `page back`. A stream rotation (step
    7) gets no marker: nothing went unheard;
  - after each candidate's utterance a `yaml carl-candidate` block: `id`,
    `kind`, `repeat_of` and `p` for a repeat of a failed candidate checked
    anew, `shown` (`plain`, `hedged` or `no`; a withdrawn card is `no`),
    `late`, `check_time_s` (the page's `card shown` age, else the card's
    age when sent), `title`, `card`, `source`, `state` for a check that
    failed, was dropped or never finished (`failed at fact-finding
    (timeout)`), `settled_by` for a settled one, `restated: {A, B}`, and
    `verdict: {A, B, same_fact, supported: [A, B], verified: [A, B],
    reason}` (outcomes shortened to `wrong`, `right`, `answered`, `not
    found`, or `failed:<kind>`, `missed`; verified as `page`, `snippet`, or
    `no:<reason>`). A repeat's block has `repeat_of` (or `unknown`) and `p`.
    Every block ends with `mark:` (a comment lists its allowed values) and
    `note:`. Events it doesn't know are skipped and every field is optional,
    so a step-2 recording is a transcript only.
- `check(markdown, events)` returns its problems, one line each with the
  file's line number. Against a fresh `generate` of the recording: the
  transcript's labels and times line by line (text may differ), lined up
  with `difflib` so a missing or added line is named; each candidate id and
  the line its block follows; repeats and their `repeat_of`. Always: `mark`
  values by the block's kind (a shown card, a candidate with no card, a
  repeat), a mark on every block with `status: done`, `status` and `format`,
  `same_speaker` groups of two labels or more that exist, `carl-missed`
  blocks with `kind` (claim, open question) and `should_say` under an
  utterance, unknown `carl-*` blocks, unclosed fences and YAML that can't be
  read. With the recording expired, the file is checked on its own.
- There is no YAML library: the module writes and reads a small subset of
  YAML 1.2 (one `key: value` a line, flow lists and mappings, JSON-escaped
  double quotes, single quotes, comments, continuation lines and `|`/`>`
  blocks for notes), described in its docstring.

**`carl owner …`** in `src/carl/owner.py` (all with `--dev`):

- `generate <id>` or `generate --all`: writes `corpus/<id>.md`. It refuses a
  recording that is gone ("stopped and deleted, has expired, or never
  was"), and keeps a corpus file whose status isn't `not started`, or that
  holds marks, notes, missed blocks or `same_speaker` groups all the same.
  `--all` goes on past kept files.
- `fetch <id> [--out FILE|DIR]`: to `~/carl-corpus/<id>.md` by default,
  never over a local file that differs.
- `check <file>` and `put <file>`: the session id comes from the header;
  `put` uploads only a file that passes, and reminds the owner when the
  status is still `not started`.
- `month [YYYY-MM]`: the month's total per provider and per stage from
  `costs/month-YYYY-MM.json`, in USD as billed, with the estimated part.

**The cost summary** (`src/carl/costs.py`, `Session.add_cost`,
`Session.cost_summary`; tests in `tests/test_cost_summary.py`):

- Every charge now goes through the session (`add_cost`): the
  speech-to-text stream's time, decision and settle calls, both
  fact-finders, verdicts and the agreement call. Each updates the session's
  tally (`SessionCosts`) as well as the month's total.
- `costs/sessions/<id>.json`, kept indefinitely, with no conversation
  content: the session id, start (UTC) and timezone, end, duration and
  listening time, the total in USD and ≈€ with its estimated part, the cost
  per stage and per provider (each `usd`, `estimated_usd`, `charges`), the
  provider's own figure less Carl's where the provider gives one
  (`provider_difference_usd`, Perplexity's and OpenRouter's), and whether
  the recording was kept, stopped or never made. Figures keep 8 decimals,
  since a decision call costs about $0.00005.
- It is written at Start, kept current with the state saves when the costs
  change (so a crash loses at most a few seconds of it), written at a
  shutdown's suspend, and for good at End. A resumed session carries its
  tally on (it is part of `state.json`).
- A stopped recording leaves only its line: `recording: "stopped"` and
  `recording_stopped: "recording stopped and deleted at hh:mm"`, in the
  session's own timezone. A stop that reaches the server after the session
  ended adds the line to the summary already written.
- At End, `costs/last-session.json` gets the Start screen's line, and every
  `hello` carries it as `costs.last_session`: `started`, `timezone`,
  `listening_s`, `cost_eur` and `eur_per_hour` (≈€ per listening hour,
  `null` for a session under a minute), or `null` before the first session.
  A new instance reads it from the store.

**The Start screen's last-session line** (`src/carl/web/`): under the month
line, "Last session: Mon 28 Sep, 1 h 30 min, ≈ €0.46 (≈ €0.31/h)" from the
hello's `costs.last_session`, the date in the session's own timezone (the
page's where the browser doesn't know it), the €/h part left out when
null, the whole line when `last_session` is null. Each part keeps
together, so the line wraps only between them. It follows every hello,
the handover's included. A session that ends on the page shows at once
from its summary (date from Start, `listening_s`, `cost_eur`, no €/h) until
the next hello brings the server's line; a summary's own `last_session`
would win if the server adds one. Checked with Playwright against a mock
at 900x420, 640x360, 420x900 and 360x740.
