# What "done" means for the first working version

Type: grilling
Status: resolved
Blocked by: 

## Question

Which behaviours of the [product spec](../../purpose-and-goal/spec.md) must the first working version have, and which can wait for a later version? For example: card history and late cards, the "Settled at the table" mark, the card archive with wrong/pointless marks, the failure log, the monthly budget warning, the live transcript line, the 30-min silence end, location. Which success-criteria targets must it meet before a real table (none: it only has to run and record?), and what must a recording session capture so the later model comparison can replay it? The answer scopes every other ticket.

## Answer

Settled with the owner in a grilling session (2026-09-25).

- **Target device:** Android Chrome on the owner's phone. iOS Safari is
  best-effort only.
- **Development mode first.** The first working version runs recording
  sessions. A normal session is the same pipeline with recording switched
  off. The **card archive** (with its wrong/pointless marks and missed-moment
  notes) waits for a later version.
- **Cards are shown live in recording sessions**, exactly as the spec
  describes, not logged silently. Check time, the table settling a point and
  late cards can only be seen live, and the table has been told it is a test.
- **Screen behaviours now:**
  - Start, End and one-tap **Pause**.
  - The **listening indicator**: listening, recording, paused, can't hear or
    check.
  - One large fact card at a time, kept until tapped away, with the
    Claim/Question labels and the hedged mark.
  - **Card history**, and **late cards** filed into it.
  - The screen kept on.
  - Location, with an off switch.
  - The drop rule: a candidate the table resolves before its card is ready
    gets no card.
- **Screen behaviours later:**
  - The "Settled at the table" mark and the **live transcript line**.
  - Setting the **monthly budget** and its warning mark.
  - The "Log" menu. The **failure log** is still written now; only viewing
    it waits.
  - The 30-minute silence end. End and closing the page still end a
    session.
- **No quality targets for "done".** Precision, recall, check time and cost
  targets belong to the later comparison map, measured on the test corpus.
  The first version is done when a 2-hour session runs end to end on the
  phone without breaking and is recorded completely, with check time and
  cost measured.
- **What a recording session captures,** so every stage can be replayed
  later:
  - the audio exactly as sent to speech-to-text;
  - every speech-to-text event with timestamps, interim segments included;
  - every model call: request, response, model id, prompt version,
    parameters, latency and cost;
  - the date, time and location context each stage was given;
  - Pause and End events, and the fact cards shown.
- **Cost is metered from the start.** The Start screen shows the month's
  running total. Setting a budget and its warning come later.

**Owner's steers for later tickets** (not decided here):

- *Provisional models for each stage:* Soniox stt-rt-v5 is the leading
  speech-to-text candidate on price. Parakeet v3 models must be evaluated
  too, since they can run locally for free.
- *Hosting and secrets:* Cloudflare is the top hosting candidate. Scaleway can
  be evaluated too. If GPU processing is ever needed, Vast.ai is the owner's
  choice.
