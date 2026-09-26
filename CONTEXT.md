# Carl

Carl is a live conversation fact-checker for private, personal use. It listens to
a conversation at a table and shows a short fact card when something said is
false or when a question goes unanswered.

## Language

### The setting

**Session**:
One stretch of listening. It starts when the owner taps Start and ends when anyone taps End, after 30 min without an utterance, or when the page is closed or loses its connection for more than 2 minutes.
_Avoid_: Conversation, run, meeting

**Owner**:
The person who runs Carl on their own phone and discloses it to the table.
_Avoid_: User, host, operator

**Table**:
Everyone taking part in the conversation Carl listens to, the owner included. All of them see every fact card.
_Avoid_: Audience, participants, room

**Access pass**:
A secret passphrase that lets a browser open Carl. The owner can issue several and revoke each one on its own; a browser that has used one stays let in for a year.
_Avoid_: Login, account, password

**Listening indicator**:
The always-visible on-screen sign that Carl is listening, that it is paused, or that it can't hear or check (connection lost, a stage down). While the month is over the monthly budget, it also carries a warning mark.
_Avoid_: Status light, recording badge

**Pause**:
A state anyone at the table can switch on with one tap, in which Carl hears and keeps nothing until someone taps again.
_Avoid_: Mute, stop

### The conversation

**Utterance**:
One final (not interim) transcript segment attributed to a single speaker.
_Avoid_: Sentence, segment, chunk

**Speaker label**:
The anonymous tag speech-to-text gives each utterance's speaker. It means the same person only within one unbroken stretch of listening; after a Pause or a gap, labels start afresh.
_Avoid_: Speaker name, speaker ID, voice

**Candidate**:
An utterance the decision model flags as worth fact-checking; either a claim or an open question.
_Avoid_: Detection, hit, trigger

**Repeat**:
An utterance that asserts the same thing, or asks the same question, as an earlier candidate in the same session, in any language or wording. It gets nothing new, unless the earlier candidate failed at a stage; then it is checked as a new candidate.
_Avoid_: Duplicate, re-trigger

**Settled**:
What a candidate becomes when a later utterance at the table corrects its claim, answers its open question or ends its disagreement, the candidate's own speaker included. A settled candidate gets no card if its card isn't on screen yet; a card on screen is marked "Settled at the table" only if the table's answer agrees with it. The settling utterance is judged as a candidate in its own right, so a false correction still gets checked.
_Avoid_: Resolved, answered, closed

**Claim**:
A candidate stating something that can be checked as true or false against a public source, given where and when the table is. Opinions, predictions, private facts and contested questions are not claims.
_Avoid_: Statement, assertion

**Open question**:
A candidate where the conversation wonders about something that a public source can answer, given where and when the table is, and the table leaves it unresolved ("what was that actor's name…"). A disagreement the table can't settle ("1953 or '54?") is an open question too.
_Avoid_: Memory lapse, unanswered question

### The pipeline

**Decision model**:
The cheap, fast stage that runs on every utterance and decides, as a typed answer rather than written text, whether it is a candidate.
_Avoid_: Detection, detector, classifier

**Fact-finding model**:
The search stage that runs only on candidates, finds out whether a claim is wrong or what answers an open question, and writes a draft card.
_Avoid_: Researcher, answerer, message writer

**Draft card**:
A fact card as the fact-finding model wrote it, with the source excerpt that backs it, before the fact-checking model has judged it. It is never shown.
_Avoid_: Proposed card, candidate card

**Fact-checking model**:
The stage that judges each draft card, as a typed answer rather than written text, and returns a verdict.
_Avoid_: Verifier, verification

**Verdict**:
The fact-checking model's typed judgement of a draft card (supported by its source, not supported, or not answering the candidate) with a probability for each.

**Fact card**:
The short message shown on screen: a title, a one-sentence fact and a source.
_Avoid_: Correction, banner, contribution

**Card history**:
The session's earlier fact cards, kept on screen out of the way of the current card, ordered by the time of their utterance, newest first.
_Avoid_: Feed, log, ledger

**Card archive**:
Earlier sessions' fact cards, grouped by session with each session's listening time (paused time excluded), and kept on the owner's phone until the owner deletes them. Between sessions the owner can mark cards wrong or pointless and add a note of missed moments. It can be opened only when no session is running.
_Avoid_: History, recap, log

**Live transcript line**:
An optional line next to the listening indicator showing the latest utterance Carl heard.
_Avoid_: Captions, subtitles

**Hedged fact card**:
A fact card whose wording ("probably") carries a verdict that is likely but not confident, or that only one fact-finding model backs. Below that band, no card is shown.
_Avoid_: Uncertain card, low-confidence card

**Verified excerpt**:
A source excerpt that Carl itself found word for word in its source, as opposed to one a model merely claims. Every shown fact card has at least one behind it.
_Avoid_: Quote, citation

**Agreement**:
Both fact-finding models reaching the same outcome for a candidate and stating the same fact. A plain fact card needs it.
_Avoid_: Consensus, concurrence, cross-check

**Check time**:
The time from the end of an utterance to its fact card on screen.
_Avoid_: Latency, delay

**Late card**:
A fact card that can't reach the screen within 20 s of its utterance, because it was ready too late or waited too long behind another card. It skips the screen and goes straight into the card history, at its place by utterance time.
_Avoid_: Stale card, expired card

**Failure log**:
The record of moments Carl couldn't hear or couldn't check: time, stage and error, with no conversation content. It can be opened at any time, and entries expire after 30 days.
_Avoid_: Error log, debug log

**Monthly budget**:
The running cost the owner sets for a month. Going over it never stops Carl; it only puts a warning on the listening indicator and the Start screen.
_Avoid_: Cost cap, limit, quota

### Testing

**Recording session**:
A session run in development mode that records audio, the full transcript and the full log of every model call for the test corpus. It is visibly marked, disclosed on its own, and anyone's objection means it doesn't record. Its audio, raw transcript and model-call logs are deleted 6 months after it was recorded; its corrected Markdown stays in the test corpus.
_Avoid_: Debug session, test session

**Test corpus**:
The owner-corrected Markdown files from recording sessions, with each fact card marked deserved or not and missed candidates added, plus the audio of those under 6 months old. The Markdown keeps speaker labels (no names) and the location rounded to neighbourhood or town, and stays until the owner deletes it. Carl's precision and recall are measured against it.
_Avoid_: Golden set, dataset, benchmark
