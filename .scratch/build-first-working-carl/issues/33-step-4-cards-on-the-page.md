# Step 4: Cards on the page

Type: task
Status: resolved
Blocked by: 

Part of [step 4](05-step-4-first-cards.md). The
[First working Carl spec](../../first-working-carl/spec.md#the-session-screen) is the source of truth.

## What to build

The current card, the card history, pacing (8 s with "+N waiting" and a
shrinking bar), late cards (20 s), and the page's reports of each card shown
or filed, as `docs/websocket.md` describes them.

## Done when

- [x] The screens work in Chromium against a local server, landscape and
      portrait.

## Answer

Built on 2026-09-27, in `src/carl/web/`.

- `cards.js` (new) paces the cards and draws the current card and the card
  history; `app.js` hands it `card` and `cards`, and sends its reports;
  `index.html` has the history list and a "Cards" row in the "Session
  ended" summary (`summary.cards`, "—" when unknown); `style.css` has the
  prototype's look (layouts P and L1).
- **The current card** fills the region left of the history (landscape) or
  above it (portrait): the coloured label (claim amber, question teal), the
  server's `tag` as a dashed pill next to it, the title, the fact (regular
  weight when hedged, as in the prototype) and the source as an underlined
  link with ↗: the source title, or the host without `www.` when the title
  is empty. Only an http(s) URL becomes a link, with `target=_blank
  rel="noopener noreferrer"`; everything is set as text. A tap on the link
  opens it and leaves the card; a tap anywhere else in the region (or Enter
  or Space on the focused card) moves on. The card's `language` goes on its
  `lang`, for hyphenation.
- **Long facts** scale down: the type is in `cqmin` of the card's region,
  times `--fit`, which `cards.js` binary-searches (down to 0.3, words kept
  whole while measuring) until nothing overflows; it refits on resize and
  when fonts load. The fact never goes below 21 px; if it still doesn't fit
  it scrolls within the card, faded at the bottom until scrolled to its
  end. Short Finnish facts come out at 31–44 px across the four sizes, a
  typical long one at 24–30 px.
- **Pacing**, on the page clock against `utterance_time`: alone, a card
  stays until tapped. With another waiting, it stays at least
  `min_on_screen_s` from when it reached the screen, then gives way by
  itself (at once if it has already been up that long); a tap moves on at
  once. "+N waiting" and a bar that shrinks to nothing at the 8 s mark show
  under the card (the row keeps its place when hidden, so the type doesn't
  jump). Waiting cards go up in utterance order. A waiting card is filed as
  late as soon as `late_card_s` has passed since its utterance, which is
  when it can no longer reach the screen in time. A tap within 0.5 s of a
  card coming up is ignored, so a tap meant for the card before doesn't
  throw the new one away unread.
- **Reports**: `card_shown` when a card reaches the screen, `card_filed`
  with `late: false` when tapped away or replaced, `late: true` when it
  skipped the screen, `at` from the page clock. They queue in order and go
  only once the server has confirmed the session on the current connection
  (after the rejoin's `session` reply), and before `end`. The location
  messages now use the same gate, which also waits for the hello.
- **The card history**: newest first by utterance time, ≠ or ?, a dashed
  edge for hedged cards, rows 2, 3 and 4+ at 82%, 66% and 52% opacity, the
  source a link opened the same way. Late cards land at their place with
  no mark.
- **`cards` after a rejoin** rebuilds the screen, but a card this page has
  already moved further (shown or filed while the connection was down, its
  report still queued) keeps the page's state, and cards the server doesn't
  list stay. The server's own current card isn't reported again. A `card`
  the page already has is ignored.
- A card that fails to render is kept in `cards.failures` (id and time) for
  step 7's buffer, never shown and never reported; the pacing carries on.
- Checked with Playwright in Chromium against a throwaway mock of
  `docs/websocket.md` that pushes cards with chosen utterance times and
  keeps their state from the reports (88 checks): a card alone stays 10 s
  until tapped; two cards pace at 8.0 s with "+1 waiting" and the bar
  shrinking; a tap moves on in about 50 ms; utterance order; a late card
  filed with `late: true` in its place, and one ready too late skipping
  the screen; the link opening a new tab and leaving the card; history
  marks, dashed edge, dimming; taps while disconnected winning over a
  stale `cards` and their reports sent after the rejoin; `cards` from
  scratch; the summary's count; screenshots at 900x420, 640x360, 420x900
  and 360x740 with short plain and long hedged Finnish facts, and rotation.
  No request left the origin. Not yet run against the real server, whose
  card messages come with ticket 32.
