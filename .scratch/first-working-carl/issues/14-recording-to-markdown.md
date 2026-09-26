# Turning a recording session into owner-correctable Markdown

Type: prototype
Status: claimed
Blocked by: 08, 11

## Question

How does the dev version turn a recording session into the Markdown file the [spec](../../purpose-and-goal/spec.md#how-wed-know-it-works) describes (cleaned transcript with speaker labels and timestamps, each candidate with its verdict summary, card text and check time), and how does the owner correct it (deserved / not deserved with a reason, missed candidates, transcript fixes)? Prototype the file and the correction workflow.

## Comments

- From [How audio is streamed and how speaker labels reach the decision model](08-audio-and-speaker-labels.md#answer): the recording keeps Soniox's raw tokens and labels; speaker labels are scoped per stream (fresh after each Pause or gap), so the owner may need to merge labels across streams when correcting.
- From [Decision model context and candidate de-duplication](09-decision-context-and-dedup.md#answer): each candidate has a standalone restatement from each fact-finder, and each repeat links to the earlier candidate it matched. The Markdown should show both so the owner can mark wrong matches.
- From [Splitting verdict confidence into plain, hedged and silent](10-confidence-bands.md#answer): each candidate that reaches fact-checking carries both draft cards, both verdicts, the agreement call, excerpt-verification results and a band reason code (e.g. `silent:contradiction`). The Markdown's verdict summary can show the reason code so the owner's deserved/not-deserved marks line up with it.
- From [Where the card archive, failure log and recording sessions are kept](11-storage-expiry-deletion.md#answer): the raw material is `recordings/<id>/` (raw PCM chunks + a JSONL event log); the corrected Markdown is `corpus/<id>.md` in the same bucket, downloaded for correction and uploaded back. The owner-only script (`list`/`fetch`/`delete`) could also host the generate step.

- From [Hosting and secrets](13-hosting-and-secrets.md#answer): the bucket is Scaleway Object Storage (fr-par), reached with a scoped S3 key; local runs write under a `dev/` prefix.
