# The WebSocket between the page and the server

One WebSocket at `/api/ws`, behind the access pass (First working Carl spec,
[One WebSocket](../.scratch/first-working-carl/spec.md#one-websocket)).
Binary frames carry audio from the page. JSON text frames carry everything
else, each an object with a `type`. Either side ignores a `type` it doesn't
know. This page lists the messages as of build step 4.

## Always

| Direction | Message | Meaning |
| --- | --- | --- |
| both | `{"type": "heartbeat"}` | Sent when nothing else was sent for `heartbeat_s` (3 s). Hearing nothing for `silence_s` (10 s) means the connection dropped |
| server → page | `{"type": "hello", "config": {…}, "costs": {"month_usd": 1.23, "month_eur": 1.08}}` | First message on every connection: the config values the page needs, and the month-to-date cost for the Start screen (`null`s when unknown) |

## A session

| Direction | Message | Meaning |
| --- | --- | --- |
| page → server | `{"type": "start", "record": true, "disclosure": {"text": "…", "confirmed_at": "2026-09-27T18:02:11.123Z"}, "mic": {…}, "timezone": "Europe/Helsinki", "start_id": "<uuid>"}` | Tap on Start. `record` is the "Record this session" switch. `disclosure` is the exact text shown (the Finnish, a blank line, the English) and when "Everyone agreed, start recording" was tapped, or `null` without recording; without both, the server doesn't record. `mic` is `track.getSettings()`. `start_id` is the page's own id for this Start: a `start` resent after a drop carries on the session it already started instead of starting another. Sent once the microphone is open |
| server → page | `{"type": "session", "session": "<id>", "state": "listening", "recording": true}` | The session's state, after start, pause, resume, rejoin and a stop. `state` is `listening` or `paused`. `recording` is true while audio is actually being written: never while paused, never after a stop |
| page → server | binary frame | About 100 ms of raw 16 kHz 16-bit little-endian mono PCM, each chunk standing alone. Only while the state is `listening`. The server handles a connection's messages in order, so audio may follow `start` or `resume` at once; the page waits for the `session` reply instead, which loses a few hundred ms |
| server → page | `{"type": "speech"}` | Speech-to-text is hearing words, at most every 500 ms: the listening indicator's dot pulses |
| page → server | `{"type": "pause"}` / `{"type": "resume"}` | Pause taps. The page stops the microphone track on pause and opens it again on resume |
| page → server | `{"type": "end"}` | End, confirmed in the top bar, or the page being hidden for good (`pagehide`) |
| server → page | `{"type": "ended", "session": "<id>", "summary": {"listening_s": 5400.0, "cost_usd": 0.18, "cost_eur": 0.16, "recording": "kept", "cards": 4, "month_eur": 1.24}}` | The session is over. `recording` is `kept`, `stopped` or `none`. `cards` counts the cards sent to the page and not withdrawn, `null` when Carl ran with no checks |

`pause`, `resume` and `end` carry no session id: they act on the session
this connection started or rejoined. After a reconnect the page sends
`rejoin` first.

## Cards

The server holds each card's state; the page paces the cards and reports
what it did with each (spec section 8, Pacing and late cards).

| Direction | Message | Meaning |
| --- | --- | --- |
| server → page | `{"type": "card", "card": {"id": "C3", "kind": "claim", "band": "hedged", "language": "fi", "label": "Väite", "tag": "Varauksin", "title": "…", "fact": "Todennäköisesti: …", "source": {"url": "https://…", "title": "…"}, "utterance_time": "2026-09-27T18:04:31.200Z", "age_s": 6.4}}` | A card ready for the screen. `kind` is `claim` or `question`; `band` is `plain` or `hedged` (`tag` is `null` for plain). `label`, `tag` and the hedge prefix in `fact` are already in the card language. `utterance_time` is when its utterance ended, for the card history's order and the recording. `age_s` is the seconds since then by the server's clock when the message was sent: the late-card cut-off counts from it, so a phone clock that is off doesn't move it. Each card in `cards` carries both too |
| server → page | `{"type": "card_withdrawn", "id": "C3"}` | The table settled the card's candidate before the card was shown: the page removes the card if it hasn't shown it yet. A card already on screen or in the card history stays as it is, since the card history never changes. A withdrawn card is left out of `cards` |
| page → server | `{"type": "card_shown", "id": "C3", "at": "…"}` | The card reached the screen |
| page → server | `{"type": "card_filed", "id": "C3", "at": "…", "late": false}` | The card went into the card history: tapped away (`late: false`), or late (`late: true`), skipping the screen |
| server → page | `{"type": "cards", "current": {…} or null, "waiting": [{…}], "history": [{…}]}` | The whole screen again, after a rejoin when the session has cards: the server is the source of truth for a session's cards. Cards that became ready while the page was away arrive here, in `waiting` |

## Reconnecting

The server keeps a session for `reconnect_grace_s` (2 minutes) after its
page's connection drops, with the speech-to-text stream kept open.

| Direction | Message | Meaning |
| --- | --- | --- |
| page → server | `{"type": "rejoin", "session": "<id>"}` | After a reconnect, the page asks to carry on with its session |
| server → page | `session` or `ended` | The session carries on, or it had already ended. The `ended` summary is `null` when the server no longer knows the session, as after a restart |

## Stopping a recording

| Direction | Message | Meaning |
| --- | --- | --- |
| page → server | `{"type": "stop_recording", "session": "<id>"}` | "Stop recording?" confirmed. The page keeps the stop in local storage until the server confirms it, and sends it again on every connection, even after the session ended |
| server → page | `{"type": "recording_stopped", "session": "<id>"}` | Everything recorded for the session is deleted and nothing more will be. The session carries on as a normal session. Every stop with a well-formed session id is confirmed, even one for a session the server no longer knows |

## Location

The Location switch on the Start screen (on the first time Carl is opened,
then remembered on the phone) is fixed at Start: `start` carries
`"location": true` or `false`, and a recording's start event keeps it. With
it off, the page never asks for location and sends none of these. With it
on, the page runs `watchPosition` while the session is listening, and stops
it on Pause and at End (First working Carl spec,
[Location](../.scratch/first-working-carl/spec.md#12-location)).

| Direction | Message | Meaning |
| --- | --- | --- |
| page → server | `{"type": "location", "fix": {"lat": 60.1841, "lon": 24.9497, "accuracy_m": 20, "time": "2026-09-27T18:04:00.000Z"}}` | A raw fix: degrees, the accuracy radius in metres, and when the phone took it. The session's first fix, then another only when the phone has moved more than `new_fix_distance_m` (500 m) from the last fix sent, or when the accuracy has moved up a level. Sent only once the server has confirmed the session; one taken while the connection is down waits for the rejoin |
| page → server | `{"type": "location", "denied": true}` | The phone refused location. Sent once, and the page doesn't ask again in that session |

The accuracy levels are the server's cuts, from the hello's
`config.location`: worse than `no_location_accuracy_m` (20 km) is no
location, worse than `town_only_accuracy_m` (1 km) is the town only, and
anything better is the full place name.

The server doesn't answer these. It turns fixes into a place name with
Nominatim (`src/carl/location.py`), and stages get only the place name and
the local date, time and timezone. Coordinates never go to any model: they
stay in server memory until End, and in a recording session's event log.
