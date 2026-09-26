# Decision model context and candidate de-duplication

Type: grilling
Status: open
Blocked by: 01, 07

## Question

How much context does the decision model get with each utterance (how many earlier utterances or seconds, speaker labels, date, time, location), which utterances skip it entirely (backchannel, very short turns), and how does Carl keep to one card per claim or open question per session: how is a candidate matched against earlier ones, and what does a repeat do?

## Comments

- From [Provisional models for each stage](07-provisional-models.md#answer): the decision model gives typed answers only (a choice with probabilities), so matching a candidate against earlier ones cannot rely on it writing a restated claim.
- From [How audio is streamed and how speaker labels reach the decision model](08-audio-and-speaker-labels.md#answer): speaker labels are only meaningful within one speech-to-text stream; a new stream (Pause, drop, restart) brings fresh labels and a "(paused)" or "(gap)" marker in the decision context. Utterances are split at speaker changes (1–2-word false switches merged) and capped at about 30 s.
