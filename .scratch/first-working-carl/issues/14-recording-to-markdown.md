# Turning a recording session into owner-correctable Markdown

Type: prototype
Status: resolved
Blocked by: 08, 11

## Question

How does the dev version turn a recording session into the Markdown file the [spec](../../purpose-and-goal/spec.md#how-wed-know-it-works) describes (cleaned transcript with speaker labels and timestamps, each candidate with its verdict summary, card text and check time), and how does the owner correct it (deserved / not deserved with a reason, missed candidates, transcript fixes)? Prototype the file and the correction workflow.

## Comments

- From [How audio is streamed and how speaker labels reach the decision model](08-audio-and-speaker-labels.md#answer): the recording keeps Soniox's raw tokens and labels; speaker labels are scoped per stream (fresh after each Pause or gap), so the owner may need to merge labels across streams when correcting.
- From [Decision model context and candidate de-duplication](09-decision-context-and-dedup.md#answer): each candidate has a standalone restatement from each fact-finder, and each repeat links to the earlier candidate it matched. The Markdown should show both so the owner can mark wrong matches.
- From [Splitting verdict confidence into plain, hedged and silent](10-confidence-bands.md#answer): each candidate that reaches fact-checking carries both draft cards, both verdicts, the agreement call, excerpt-verification results and a band reason code (e.g. `silent:contradiction`). The Markdown's verdict summary can show the reason code so the owner's deserved/not-deserved marks line up with it.
- From [Where the card archive, failure log and recording sessions are kept](11-storage-expiry-deletion.md#answer): the raw material is `recordings/<id>/` (raw PCM chunks + a JSONL event log); the corrected Markdown is `corpus/<id>.md` in the same bucket, downloaded for correction and uploaded back. The owner-only script (`list`/`fetch`/`delete`) could also host the generate step.

- From [Hosting and secrets](13-hosting-and-secrets.md#answer): the bucket is Scaleway Object Storage (fr-par), reached with a scoped S3 key; local runs write under a `dev/` prefix.

## Answer

Settled with the owner by reacting to a prototype (2026-09-26): three shapes
of the same fictional dinner in
[prototypes/recording-markdown/](../prototypes/recording-markdown/README.md).
The owner chose **variant C, "blocks"**
([variant-c-blocks.md](../prototypes/recording-markdown/variant-c-blocks.md)).

**The file (`corpus/<id>.md`)**

1. **A header block** (fenced `yaml carl-session`): session id, place (rounded
   to neighbourhood or town), listening time, config file and hash, cost,
   correction `status` (`not started / in progress / done`), and
   `same_speaker` pairs where the owner merges labels across streams
   (e.g. `[[A2, B1]]`), no names.
2. **The transcript** as readable lines, `**A2** · 00:04:31 · text`, time
   counted from Start, small talk and skipped backchannel included, with
   "paused" and "gap" markers at stream boundaries.
3. **Every candidate as a fenced `yaml carl-candidate` block** right after its
   utterance, filled in by the generator: Carl's id (C1…), kind, shown
   (`plain / hedged / no`), late, check time, card text and source, both
   fact-finders' restatements, the verdict summary (both outcomes,
   p(same fact), p(supported) per card, how each excerpt was verified, and
   ticket 10's band reason code). A repeat's block carries `repeat_of: Cn`
   and its probability.
4. **Owner fields** in each block: `mark` and `note`. Values:
   - shown card: `deserved`, or the spec's reasons `wrong / nitpick /
     opinion / contested / already settled / not checkable`;
   - silent candidate: `ok` or `should show` (so the bands can be tuned for
     recall too);
   - repeat: `ok` or `bad match` (the note says what it should have been).
5. **Missed candidates**: the owner adds a `yaml carl-missed` block (`kind`,
   `should_say`) under the utterance Carl should have caught.
6. **Transcript fixes only around candidates**: the owner fixes errors that
   change a candidate, a missed one or the context they need, and leaves the
   rest as speech-to-text heard it. The corpus is therefore not a
   word-error-rate reference; the comparison map must build its own if it
   wants one.

**The workflow** (commands on the owner-only script from
[Where the card archive, failure log and recording sessions are kept](11-storage-expiry-deletion.md#answer)):

7. `generate <id>`: a pure function of `recordings/<id>/`'s event log that
   writes `corpus/<id>.md`; it refuses to overwrite a file whose status isn't
   `not started`, so corrections are never lost. Run by hand after the
   session, so the format can change and drafts be regenerated until
   correction starts.
8. `fetch <id>` downloads it; the owner edits it in any editor.
9. `put <file>` runs `check` and uploads over `corpus/<id>.md`. `check`
   rejects unknown mark values, changed or missing candidate ids, utterance
   times or speaker labels, and `same_speaker` labels that don't exist; with
   `status: done` it also requires a mark on every candidate and repeat block.

No new domain terms and no ADR: the format and script are cheap to change,
and every file records its format version.
