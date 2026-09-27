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
- **Pacing**, on the page's monotonic clock (`performance.now()`): alone, a
  card stays until tapped. With another waiting, it stays at least
  `min_on_screen_s` from when it reached the screen, then gives way by
  itself (at once if it has already been up that long); a tap moves on at
  once. "+N waiting" and a bar that shrinks to nothing at the 8 s mark show
  under the card (the row keeps its place when empty, so the type doesn't
  jump). Waiting cards go up in utterance order. A waiting card is filed as
  late as soon as `late_card_s` has passed since its utterance, which is
  when it can no longer reach the screen in time. That deadline is the
  moment the page received the card plus `late_card_s − age_s`, so the
  phone's and the server's clocks needn't agree; without `age_s` it falls
  back to `utterance_time` against the page's clock, an utterance time in
  the future counting as age 0. The same goes for cards in `cards`.
  `utterance_time` still orders the waiting cards and the history. A tap
  within 0.5 s of a card coming up is ignored, so a tap meant for the card
  before doesn't throw the new one away unread.
- **While the page is hidden** (`visibilityState` not `visible`: a source
  open in another tab, the phone locked), pacing waits: the card on screen
  stays, its 8 s count only visible time and the bar stands still, no
  waiting card comes up and no `card_shown` is sent. The late-card cut-off
  keeps running, so a card that passes it while hidden goes into the
  history as late. When the page is visible again, pacing carries on, and a
  card that arrived meanwhile comes up at once if nothing is on screen.
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
  keeps their state from the reports, sends `age_s` at send time and can
  skew `utterance_time` or leave `age_s` out (112 checks): a card alone
  stays 10 s until tapped; two cards pace at 8.0 s with "+1 waiting" and the bar
  shrinking; a tap moves on in about 50 ms; utterance order; a late card
  filed with `late: true` in its place, and one ready too late skipping
  the screen; the link opening a new tab and leaving the card; history
  marks, dashed edge, dimming; taps while disconnected winning over a
  stale `cards` and their reports sent after the rejoin; `cards` from
  scratch; the summary's count; a server clock 40 s behind or 60 s ahead
  not changing which cards are late, the deadline landing 20 − `age_s`
  after receipt (5.0 s for age 15), 19.3 s coming up and 20.3 s late, the
  `utterance_time` fallback, `age_s` deciding inside `cards`; with the page
  made hidden (an init script, since Playwright can't hide a page), the
  card on screen staying 10 s with its bar still, the waiting card coming
  up after 8 s of visible time in all (within 6 ms), a card arriving while
  hidden coming up as the page returns, and one passing the cut-off while
  hidden filed late in its place; screenshots at 900x420, 640x360, 420x900
  and 360x740 with short plain and long hedged Finnish facts, and rotation.
  No request left the origin. Not yet run against the real server, whose
  card messages come with ticket 32.
