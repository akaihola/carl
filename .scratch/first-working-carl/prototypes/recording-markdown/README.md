# PROTOTYPE (throwaway): recording session → owner-correctable Markdown

Answers ticket [Turning a recording session into owner-correctable Markdown](../../issues/14-recording-to-markdown.md).
Three structurally different shapes of `corpus/<id>.md` for the same fictional
dinner excerpt (Einstein myth, Casablanca question, a repeat, a contradiction,
a Pause, a wrong hedged card, a missed Sibelius claim). Open them side by side.

| Variant | Where marks live | Syntax | Good at | Weak at |
| --- | --- | --- | --- | --- |
| [A inline](variant-a-inline.md) | under the utterance | checkboxes + quote blocks, ids in HTML comments | reads like the dinner; renders nicely | parsing checkboxes and free text back is fragile; ids hidden, easy to break |
| [B ledger](variant-b-ledger.md) | one table at the top | YAML front matter, Markdown tables, transcript in a code block | all marks in one place; quick to scan | long card text in table cells is painful to edit; judging a mark means jumping to the transcript |
| [C blocks](variant-c-blocks.md) | under the utterance | fenced `yaml carl-*` blocks | context right there *and* strictly parseable; checker can reject bad values | more visual noise than A |

## The workflow sketched (same for all variants)

The owner-only script from [ticket 11](../../issues/11-storage-expiry-deletion.md) grows three commands:

1. `generate <id>`: a pure function of `recordings/<id>/events.jsonl` →
   `corpus/<id>.md`. Refuses to overwrite a file whose status isn't `not
   started` (so corrections are never lost).
2. `fetch <id>` → local file; the owner edits in any editor.
3. `put <file>`: runs `check` first (every shown card and repeat marked, only
   known values, utterance ids/times and candidate ids untouched, `same_speaker`
   labels exist), then uploads over `corpus/<id>.md`.

Transcript fixes are plain edits of the utterance text; replay tooling later
diffs them against the raw Soniox tokens kept in `recordings/<id>/` by
utterance id.
