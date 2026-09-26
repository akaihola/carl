# Where the card archive, failure log and recording sessions are kept

Type: grilling
Status: resolved
Blocked by: 04, 06

## Question

Where are the failure log and recording sessions (audio, raw transcript, model-call logs, corrected Markdown) stored, and how do the 30-day failure-log expiry, the 6-month recording-session expiry and deletion requests from anyone at the table work in practice? Also say where the card archive will live once a later version adds it, so nothing now blocks it.

## Comments

- From [How audio is streamed and how speaker labels reach the decision model](08-audio-and-speaker-labels.md#answer): audio reaches the server as raw 16 kHz 16-bit mono PCM (~115 MB/h); whether recordings keep it raw or compress it is for this ticket. Recordings also keep Soniox's raw tokens with speaker labels and the microphone settings.

## Answer

Settled with the owner in a grilling session (2026-09-26).

1. **Recording sessions live on the server,** in EU-only object storage from
   whichever host [Hosting and secrets](13-hosting-and-secrets.md) picks (R2
   if Cloudflare), everything for one session under
   `recordings/<session-id>/`. The page stores none of it.
2. **Audio is kept as raw 16 kHz PCM exactly as sent** to speech-to-text
   (~230 MB per 2 h session, a few GB over 6 months, cents a month), so a
   speech-to-text replay hears exactly what the live one heard. FLAC can be
   added later without loss.
3. **Written as the session runs,** not at End: audio in roughly one-minute
   chunk objects, plus a JSONL event log (speech-to-text events, model calls,
   Pause/End, cards shown, location context) flushed about every 10 s. A
   crash loses at most one audio chunk and a few seconds of log.
4. **The test corpus lives in the same bucket** as `corpus/<session-id>.md`,
   with no expiry: one master copy, so a deletion request has one place to
   clear. The owner downloads it to correct it and uploads it back; the
   workflow is for
   [Turning a recording session into owner-correctable Markdown](14-recording-to-markdown.md).
5. **The 6-month expiry is a bucket lifecycle rule** on `recordings/`
   (delete 180 days after written; runs daily, up to 24 h late). `corpus/`
   has no rule. No backups or versioning of `recordings/`, so expired or
   deleted material is really gone.
6. **The failure log lives on the server** in its own small store (e.g.
   Durable Object storage or one object per day) with a 30-day expiry in the
   same way. The page buffers its own failures (dropped connection, lost mic)
   in memory and sends them on reconnect. Recording sessions also copy
   failures into their event log. The owner's "clear" waits for the Log menu.
7. **The card archive (later version) lives on the phone:** at End the page
   pulls the session's cards and listening time from the server into
   IndexedDB with `persist()`, offers export, and the server deletes its copy
   once the page confirms. Now: the server keeps each session's cards in its
   session state until End; a normal (non-recording) session's cards are
   discarded at End. Nothing in the first version blocks the archive.
8. **Access and deletion requests go through a small owner-only script** run
   from the owner's computer against the bucket: `list` (by date, time and
   duration), `fetch <id>`, `delete <id>`, where delete removes both
   `recordings/<id>/` and `corpus/<id>.md`. An in-app page can come later.
   Providers' own copies are outside Carl's control (the spec allows them and
   the docs name their terms).
9. **No encryption beyond the host's default** at rest plus owner-only
   access: the server needs plaintext for replays, and own keys add risk for
   little gain.

No ADR: each choice is cheap to reverse (formats, prefixes, a script).
No new domain terms.
