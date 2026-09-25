# Carl

Carl is a live conversation fact-checker for private, personal use. It listens to
a conversation at a table and shows a short fact card when something said is
false or when a question goes unanswered.

## Language

### The setting

**Session**:
One stretch of listening. It starts when the owner taps Start and ends when anyone taps End, after 30 min without an utterance, or when the page is closed.
_Avoid_: Conversation, run, meeting

**Owner**:
The person who runs Carl on their own phone and discloses it to the table.
_Avoid_: User, host, operator

**Table**:
Everyone taking part in the conversation Carl listens to, the owner included. All of them see every fact card.
_Avoid_: Audience, participants, room

**Listening indicator**:
The always-visible on-screen sign that Carl is listening, that it is paused, or that it can't hear or check (connection lost, a stage down, cost cap reached).
_Avoid_: Status light, recording badge

**Pause**:
A state anyone at the table can switch on with one tap, in which Carl hears and keeps nothing until someone taps again.
_Avoid_: Mute, stop

### The conversation

**Utterance**:
One final (not interim) transcript segment attributed to a single speaker.
_Avoid_: Sentence, segment, chunk

**Candidate**:
An utterance the decision model flags as worth fact-checking; either a claim or an open question.
_Avoid_: Detection, hit, trigger

**Claim**:
A candidate stating something that can be checked as true or false against a public source, given where and when the table is. Opinions, predictions, private facts and contested questions are not claims.
_Avoid_: Statement, assertion

**Open question**:
A candidate where the conversation wonders about something that a public source can answer, given where and when the table is, and the table leaves it unresolved ("what was that actor's name…"). A disagreement the table can't settle ("1953 or '54?") is an open question too.
_Avoid_: Memory lapse, unanswered question

### The pipeline

**Decision model**:
The cheap, fast stage that runs on every utterance and decides whether it is a candidate.
_Avoid_: Detection, detector, classifier

**Fact-checking model**:
The stronger, slower stage that runs only on candidates and returns a verdict.
_Avoid_: Verifier, verification

**Verdict**:
The fact-checking model's result for a candidate: outcome, answer, source and confidence.

**Message-writing model**:
The stage that turns a confident verdict into a fact card.

**Fact card**:
The short message shown on screen: a title, a one-sentence fact and a source.
_Avoid_: Correction, banner, contribution

**Card history**:
The session's earlier fact cards, kept on screen out of the way of the current card, newest first.
_Avoid_: Feed, log, ledger

**Card archive**:
Earlier sessions' fact cards, grouped by session and kept on the owner's phone until the owner deletes them. It can be opened only when no session is running.
_Avoid_: History, recap, log

**Live transcript line**:
An optional line next to the listening indicator showing the latest utterance Carl heard.
_Avoid_: Captions, subtitles

**Hedged fact card**:
A fact card whose wording ("probably", "maybe") carries a verdict that is likely but not confident. Below that band, no card is shown.
_Avoid_: Uncertain card, low-confidence card

**Check time**:
The time from the end of an utterance to its fact card on screen.
_Avoid_: Latency, delay

**Late card**:
A fact card ready more than 20 s after its utterance. It skips the screen and goes straight into the card history, at its place by utterance time.
_Avoid_: Stale card, expired card

**Failure log**:
The record of moments Carl couldn't hear or couldn't check: time, stage and error, with no conversation content. It can be opened at any time, and entries expire after 30 days.
_Avoid_: Error log, debug log

### Testing

**Recording session**:
A session run by the dev version of Carl (development mode) that records audio, the full transcript and the full log of every model call for the test corpus. It is visibly marked, disclosed on its own, and anyone's objection means it doesn't record. Each one is deleted 6 months after it was recorded.
_Avoid_: Debug session, test session

**Test corpus**:
The owner-corrected Markdown files and audio from recording sessions, with each fact card marked deserved or not and missed candidates added. Carl's precision and recall are measured against it.
_Avoid_: Golden set, dataset, benchmark
