# The can't-hear-or-check state and the failure log

Type: grilling
Status: resolved
Blocked by: 

## Question

Which signals from each stage flip the listening indicator to "can't hear or
check", when does it flip back, and what does the failure log record for
each (time, stage, error; no conversation content)?

Known signals so far: a dropped page–server connection, the 2-minute
reconnect grace period, a server restart, the speech-to-text connection
dropping while the server reopens it with backoff, the Scaleway handover at
~50 min, `overload` (more than 8 live candidates) and the 60 s candidate
timeout (from [Tracking a candidate until its card](18-tracking-candidate-until-card.md#answer)).
Open: does one failed candidate flip the indicator, or only a stage failing
repeatedly (how many, over what window)? Does a fact-finder down but the
other up count? How does the page show it, and which failures does the page
buffer itself?

## Answer

Settled with the owner in a grilling session (2026-09-26).

**One state, two wordings**

1. The listening indicator has one "can't hear or check" state, shown as
   "Ei kuule / Can't hear" or "Ei voi tarkistaa / Can't check". The server
   sends a reason code. If both apply, "can't hear" wins. How it looks is for
   [The screen](24-the-screen.md).
2. The time the indicator spends in this state is an **outage** (new term in
   `CONTEXT.md`).

**Can't hear**

3. Any of these flips the indicator:
   - **The page–server connection drops.** The page flips as soon as the
     WebSocket closes, or when no server message (heartbeat or other)
     arrives for 10 s.
   - **The mic is lost.** The mic track ends or is muted: permission revoked,
     a phone call takes the mic, or the page is hidden.
   - **The speech-to-text connection drops** while the server reopens it with
     backoff.
   - **No audio arrives:** while listening, the server receives no audio chunk
     for 5 s.

   The 10 s and 5 s limits are in config. A server restart shows up as a
   dropped connection.
4. **Not failures:**
   - the planned ~50-min handover, unless the new socket fails to open (then
     it counts as a dropped connection);
   - Pause, which has its own indicator state;
   - long silence at the table.
5. **Back:** as soon as audio flows end to end again: the socket is back, the
   mic is live, the speech-to-text stream is open and audio is arriving.

**Can't check**

6. **One failed candidate is silent;** only a stage that is down flips the
   indicator:
   - The **decision model** (and the settle call on the same model) is down
     after **3 consecutive failed calls**.
   - **Fact-finding** and **fact-checking** are down after **2 consecutive
     failed candidates**.
   - A failure is any typed error: timeout, unavailable, rate-limited or bad
     output.
   - All thresholds are in config.
7. **Back** on the stage's first success. There are no health probes, so a
   fact-finding or fact-checking outage lasts until the next candidate
   succeeds.
8. **One fact-finder down, the other up, is not "can't check".** Carl still
   checks with the other (hedged cards only, per
   [Splitting verdict confidence](10-confidence-bands.md#answer)). Each
   failure is logged as `fact-finding A` or `fact-finding B`. Fact-finding
   counts as failed for a candidate only when both fact-finders fail on it.
9. **`overload`** (more than 8 live candidates) is logged and never flips the
   indicator: the table is busy, nothing is broken. The **60 s candidate
   timeout** is logged against the stage the candidate was stuck in and
   counts as a failure of that stage for rule 6.
10. **Utterances during a decision outage are dropped,** not retried later,
    because a card minutes late is worthless. The outage entry counts them. A
    repeat said after recovery is checked as usual.

**The failure log**

11. **An entry** holds:
    - time;
    - stage (`speech-to-text`, `decision`, `settle`, `fact-finding A`/`B`,
      `fact-checking`, `connection`, `mic`);
    - kind (`timeout`, `unavailable`, `rate-limited`, `bad-output`, `dropped`,
      `overload`, `lost-in-restart`, `no-audio`, `mic-lost`);
    - provider and model id;
    - HTTP status or the provider's error code;
    - session id;
    - Carl's own candidate id (`C3`) when there is one.

    **Outages** get a start and an end, plus the skipped-utterance count. There
    is **no free-text provider message**, since some echo the prompt. A
    recording session's event log keeps the full error text for debugging.
12. **The page buffers what only it can see**, in memory, and sends it on
    reconnect (as [ticket 11](11-storage-expiry-deletion.md#answer) decided):
    - the connection gap, with its start and end;
    - mic lost (track ended or muted, or permission revoked);
    - the page being hidden;
    - the wake lock being refused or released during a session;
    - a card that failed to render.

    A wake-lock loss alone doesn't flip the indicator; only the mic actually
    stopping does.

**Recording during an outage**

13. While speech-to-text is being reopened but audio still reaches the server,
    the recording **keeps writing that audio** and the recording dot stays
    on. The event log marks the speech-to-text gap, so a replay knows the live
    run didn't hear it. This refines "a recording keeps exactly what the live
    pipeline saw" from
    [What runs in the browser and what runs on a server](06-browser-and-server-split.md#answer).
    When the page–server connection drops, no audio reaches the server and the
    dot goes off.

No ADR: every rule is a threshold or a config change away from reversal.
