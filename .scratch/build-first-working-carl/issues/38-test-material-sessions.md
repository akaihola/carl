# Test material for the phone sessions

Type: task
Status: open
Waiting on: owner

For the owner. Steps 2–8 are built and deployed together, so what's left
in tickets [03](03-step-2-recorder.md) to [09](09-step-8-corpus-and-costs.md)
is mostly phone sessions "at a real dinner or with Finnish talk playing
beside it" ([Ground rules](../../first-working-carl/spec.md#ground-rules)).
This ticket picks the talk and plans the sessions so that three runs close
those boxes and rehearse [step 9](10-step-9-acceptance.md)'s dinner. Step 9
itself needs a real dinner; nothing here closes it.

Why recorded talk and not radio: Yle Puhe, Finland's all-talk channel,
[closed on 2024-01-07](https://yle.fi/a/74-20016858). Yle Radio 1 is the
nearest left, and it still plays classical music on weekdays at 7–8, in
the 11 o'clock hour and after 16. Commercial stations play music. A
recording also gives every run the same audio.

The owner started a phone session with a radio talk show on 2026-09-27
(ticket 03's comments). Whatever boxes it ticks, these sessions only need
to close what's left.

## The material

Chosen on 2026-09-27. Lengths are from the RSS feeds and the stream's
playlist; the files and streams were checked to download.

| Material | Length | Speakers | What it tests |
| --- | --- | --- | --- |
| [Futucast](https://www.futucast.com/) #370, "Futucast Debatti: Pitäisikö kannabis laillistaa? \| Coel Thomas vs. Kai Lintunen", 2023-06-26 | 2 h 20 min | Host and two debaters, one for and one against | Claims one after another, statistics, repeats, and opinions and contested evidence that should get no card |
| Futucast #611, "Suomalaisen kommunismin ruumiinavaus \| Pekka Virkki", 2026-03-30 | 2 h 01 min | Host and an author | Finnish history: the labour movement, 1917–18, SKP and Kuusinen, the war, Kekkonen. Mostly right, so a card on a correct statement is a precision error |
| [Parliament's plenary session 53/2026](https://verkkolahetys.eduskunta.fi/fi/taysistunnot/taysistunto-53-2026), Thursday 2026-05-21 at 16 | 4 h 08 min | About 99 speeches | Question time, then the Chancellor of Justice's report for 2025, the animal-rights citizens' initiative (KAA 8/2023), electricity market law 65 b §, fuel sustainability criteria and emissions trading, Yle's supervisory board report for 2025, the language legislation report for 2025 and a municipal law motion. Many speakers, the same point made by many MPs, rhetoric, some Swedish |

Getting the audio:

```sh
curl -L -o futucast-370.mp3 'https://anchor.fm/s/f559ed68/podcast/play/85898126/https%3A%2F%2Fd3ctxlq1ktw2nl.cloudfront.net%2Fstaging%2F2024-3-25%2F375521602-48000-2-af17215d20d96dc2.mp3'
curl -L -o futucast-611.mp3 'https://traffic.megaphone.fm/APO5057060661.mp3'
ffmpeg -i 'https://eduskunta-od-eu-w-1.videosync.fi/vod-hls-eduskunta/events/mp4:events/eduskunta/6a0da03b02161746e894aedd/video/taysistunto_2152026_klo_16_2_stream1/playlist.m3u8?wowzaaudioonly' \
  -vn -ac 1 -ar 16000 -c:a pcm_s16le eduskunta-2026-05-21.wav   # about 475 MB
```

The `ffmpeg` line is untested: the playlist answers, but the environment
that checked it had no ffmpeg.

**Cost:** Soniox costs $0.12 an hour and a checked candidate about $0.03
(ticket 06's live candidate), so even 50 candidates an hour stays under
$2 an hour.

## The sessions

In this order, then step 9's dinner.

### Session 1: Futucast #370 on the phone, uninterrupted

- **Setup:** the deployed Carl; the phone unplugged; Record on and Location
  on, as at a dinner; a laptop or speaker 1–2 m from the phone at
  conversation volume. Note the battery level and the time at Start.
- **During:** nothing. Let it play to the end, then End.
- **Afterwards:**
  - the battery level and how warm the phone got: ticket 03's Android
    2-hour check;
  - `carl owner export <id>`: a playable WAV and the event log (ticket 03);
  - the event log: candidates and repeats (ticket 04), cards shown live
    (ticket 05), the plain and hedged split (ticket 06), and no gap at the
    handover (ticket 08's first box);
  - the cost summary and the Start screen's last-session line (ticket 09);
  - `carl owner generate <id>`, `fetch`, correct, `put`: ticket 09's
    corrected corpus file.
- **Marking:** the debate is from June 2023, and some of it has changed
  since (Germany legalised cannabis on 2024-04-01). Mark a card by the facts
  on the session's date, since that is what a table would hear, and say in
  the note when the claim was still true in 2023. Policy positions are
  `opinion`; disputed evidence is `contested`.

### Session 2: Futucast #611 on the phone, interrupted

- **Setup:** as session 1.
- **During:**
  - at about 20 min, airplane mode for about 30 s: the screen rebuilds with
    its cards (ticket 07) and the dropped connection recovers (ticket 08);
  - at about 40 min, Pause for a minute, then resume (ticket 08);
  - at about 1 h, restart the server with
    `scw container container redeploy <id>` (ticket 08). The session should
    resume from its saved state.
- **Afterwards:** each interruption's state and recovery, for ticket 08's
  second box. Kept apart from session 1 so that one stays a clean 2-hour
  run.

### Session 3: Parliament through `dev-send`, locally

- A local `carl serve` (see [operations](../../../docs/operations.md#running-it-locally)),
  then `uv run carl dev-send eduskunta-2026-05-21.wav --record`, at the
  default `--speed 1`: check times, late cards and settling assume real
  time. Local runs write under `dev/`, so the owner script needs `--dev`.
- It tests many speaker labels, repeats across speeches, the cap of 8,
  rhetoric that should get no card, Swedish speech, speech-to-text stream
  rotation and cost over 4 hours. A local server has no 60-minute cut, so
  the container handover isn't tested.
- It closes no box, since it isn't on the phone. It is the last rehearsal
  before the dinner.

### Also: `delete` on a throwaway

Ticket 03's `delete` box: a 2-minute recording made just for it, so the
recordings above are kept.

## The test corpus

These recordings join the test corpus next to the dinners, and a phone
session with a speaker looks just like a dinner in its corpus file. Ticket
[39](39-corpus-material-field.md) adds a header field for that. Until it
is built, each session's id and material go under `## Answer` here.

## Done when

- [ ] Session 1 ran, and its boxes are ticked in tickets 03, 04, 05, 06, 08
      and 09, with ticket 03's Android 2-hour check written.
- [ ] Session 2 ran, and ticket 07's box and ticket 08's second box are
      ticked.
- [ ] Session 3 ran through `dev-send`, with a note here on what it showed.
- [ ] `delete` was tried on a throwaway recording (ticket 03).
- [ ] Each session's id and material are listed under `## Answer` here.
