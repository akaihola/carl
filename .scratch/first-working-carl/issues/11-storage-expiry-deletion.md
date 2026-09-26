# Where the card archive, failure log and recording sessions are kept

Type: grilling
Status: claimed
Blocked by: 04, 06

## Question

Where are the failure log and recording sessions (audio, raw transcript, model-call logs, corrected Markdown) stored, and how do the 30-day failure-log expiry, the 6-month recording-session expiry and deletion requests from anyone at the table work in practice? Also say where the card archive will live once a later version adds it, so nothing now blocks it.

## Comments

- From [How audio is streamed and how speaker labels reach the decision model](08-audio-and-speaker-labels.md#answer): audio reaches the server as raw 16 kHz 16-bit mono PCM (~115 MB/h); whether recordings keep it raw or compress it is for this ticket. Recordings also keep Soniox's raw tokens with speaker labels and the microphone settings.
