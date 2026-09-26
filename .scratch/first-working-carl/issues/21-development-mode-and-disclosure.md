# Development mode and the recording-session disclosure

Type: grilling
Status: resolved
Blocked by: 

## Question

Development mode isn't a separate deployment (see
[Hosting and secrets](13-hosting-and-secrets.md#answer)). How does it work?

- Is a recording session chosen with a Start-screen switch, per session, or
  something else, and which access passes may start one?
- What does the disclosure look like on screen, and does Carl require a
  confirmation before recording starts?
- The spec says anyone's objection means the session runs without
  recording. How does someone object mid-session: a stop-recording tap that
  turns it into a normal session, and what happens to what was already
  recorded (kept, or deleted with the owner's script)?
- How does the listening indicator show recording, and what does Pause do
  to it?

## Answer

Settled with the owner in a grilling session (2026-09-26).

1. **Chosen per session on the Start screen.** A "Record this session"
   switch, **off by default every time**, fixed at Start. Development mode is
   nothing more than this switch: the same deploy, the same pipeline.
2. **Any access pass may start one.** All passes are the owner's own
   browsers; pass roles can come if a pass is ever given to someone else.
   Only the owner's bucket script reads recordings, whatever the pass.
3. **A disclosure screen, confirmed every time.** With the switch on, Start
   opens a screen showing the recording disclosure line for the owner to read
   aloud (Finnish, English below), with "Everyone agreed, start recording",
   "Start without recording" and Back. No "don't show again". The event log
   records the confirmation and the exact text shown. Carl still makes no
   announcement of its own.
4. **The disclosure text** (the location clause drops out when location is
   off):
   - *FI:* "Tämä on testi. Carl tallentaa keskustelun äänen ja tekstin sekä
     puhelimen sijainnin. Ääni ja raakalokit poistuvat 6 kuukauden kuluttua;
     korjattu teksti ilman nimiä säilyy siihen asti, kunnes poistan sen. Vain
     minä ja testattavat tekoälypalvelut käsittelevät niitä. Kuka tahansa voi
     pyytää lopettamaan tallennuksen."
   - *EN:* "This is a test. Carl records the conversation's audio and text
     and the phone's location. Audio and raw logs are deleted after 6 months;
     the corrected text, without names, stays until I delete it. Only I and
     the AI services being tested handle them. Anyone can ask to stop the
     recording."
5. **Objecting mid-session: a one-way stop that deletes.** Tapping the
   recording mark opens "Stop recording?". Confirming turns the session into
   a normal session from that moment and **deletes everything recorded so far
   at once** (`recordings/<id>/`; no corpus file is ever made). Recording
   can't be switched back on; recording again means End and a fresh Start
   with a fresh disclosure. "Don't record the next bit" is what Pause is for.
6. **What a stop leaves:** only the session's cost summary (no conversation
   content), with one line "recording stopped and deleted at hh:mm". It is not
   a failure, so the failure log gets nothing.
7. **A stop while the connection is down is never lost.** The mark goes off
   on the page at once; the page resends the stop on reconnect, and if the
   session ends first it keeps the stop in local storage and sends it the
   next time Carl opens. The server applies it whenever it arrives. No audio
   reaches the server meanwhile, so nothing new is recorded.
8. **The listening indicator's recording mark** is a red dot with
   "Tallennetaan / Recording", shown **whenever audio is actually being
   written**, on top of whichever state the indicator shows (not a fifth
   state). Pause hides it (nothing is heard or kept) and resume brings it
   back; in the can't-hear-or-check state it shows only if audio still
   reaches storage; after a stop it is gone for good.

No ADR: each choice is cheap to reverse. `CONTEXT.md` updated: the listening
indicator's recording mark, and a recording session's one-way stop.
