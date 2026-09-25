# What a phone browser lets a web page do for Carl

What current iOS Safari (in a tab and as a Home Screen web app) and Android
Chrome allow a plain web page to do with the microphone, the screen, location,
the network and, above all, storage. Compiled 2026-09-25 for
[.scratch/first-working-carl/issues/04-phone-browser-capabilities.md](../../.scratch/first-working-carl/issues/04-phone-browser-capabilities.md).

## How this was researched, and how far to trust it

- **[verified]** marks a claim checked against the cited primary page: WebKit
  blog posts and bug reports, Chrome developer and web.dev articles, MDN.
- **[compat]** marks a version number read from MDN's browser-compat-data
  (`@mdn/browser-compat-data` 8.1.3, built 2026-09-24), the data behind MDN's
  compatibility tables. "iOS" below means Safari on iOS; every iOS browser uses
  WebKit, so the same limits apply to Chrome and Firefox on iPhone.
- **[code]** marks behaviour read directly from WebKit or Chromium source on
  `main` as of today.
- **[judgement]** marks inference or widely reported behaviour that no primary
  source here states outright. Nothing in this note was tested on a device;
  the first prototype should confirm the [judgement] items.

## Summary

1. **Microphone capture works on both, with or without install.** getUserMedia
   and AudioWorklet are available in iOS Safari tabs and Home Screen web apps
   (iOS 14.5+) and in Android Chrome. Android Chrome lets the page turn echo
   cancellation, noise suppression and automatic gain control off one by one;
   iOS exposes only `echoCancellation`, so the page cannot switch noise
   suppression or gain control on its own there.
2. **iOS stops hearing when the page is hidden.** WebKit on iOS mutes the
   microphone as soon as the page is not visible (other tab, other app, screen
   locked). Android Chrome keeps capturing in the background behind a
   "using your microphone" notification. On both, **the screen must stay on**
   for a reliable session, which the Screen Wake Lock API now allows on both
   (iOS Home Screen web apps only since iOS 18.4).
3. **Storage survives on Android Chrome unless the phone runs out of space;
   on iOS Safari it depends on how Carl is opened.** In a Safari tab, all
   script-writable storage (IndexedDB, Cache API, OPFS and the rest) is
   deleted after seven days of Safari use without the owner interacting with
   Carl's site. A Home Screen web app keeps its own day counter that only runs
   while the app is used, and WebKit grants `navigator.storage.persist()`
   mainly to Home Screen web apps. Home Screen storage is **separate** from
   Safari's: data kept in the tab is not visible in the installed app.
4. **Quota is not the problem.** Both browsers let one site use up to 60% of
   the disk. Two hours of 16 kHz mono audio is about 230 MB as 16-bit PCM and
   about 22 MB as 24 kbit/s Opus; a year of card archive text is well under
   1 MB.
5. **Export works on both.** A download link to a Blob and the share sheet
   (Web Share with files) work on both; Android Chrome also has a real "Save
   as" picker (`showSaveFilePicker`, Chrome 132+).

## Microphone capture

### getUserMedia and permission

- getUserMedia: Android Chrome 53+, iOS 11+ **[compat]**. It works in Home
  Screen web apps since iOS 13.4 ([WebKit bug 185448](https://bugs.webkit.org/show_bug.cgi?id=185448),
  resolved fixed) **[verified]**. Both require HTTPS.
- On iOS, only one page can capture at a time; when another tab starts
  capturing, the first page's tracks go silent and fire `mute`. The owner can
  also pause capture from Safari's own UI, which sends silence and fires
  `mute` ([WebKit: A Closer Look Into WebRTC](https://webkit.org/blog/7763/a-closer-look-into-webrtc/))
  **[verified]**. Carl should listen for `mute`/`unmute` and reflect them in
  the listening indicator.
- In standalone Home Screen apps, route changes (for example hash-route
  changes) have caused repeated permission prompts
  ([bug 185448](https://bugs.webkit.org/show_bug.cgi?id=185448), comments;
  [bug 212040](https://bugs.webkit.org/show_bug.cgi?id=212040) "User media
  tracks muted after route change in standalone pwa") **[verified]**. A
  single-page app that never navigates avoids this. How often iOS re-asks for
  the microphone between sessions was not established **[judgement: test]**.

### Processing constraints (echo cancellation, noise suppression, gain)

For far-field table audio these matter: phone voice processing is tuned for a
talker near the phone, and can suppress distant voices or pump the gain.

| Constraint | Android Chrome | iOS Safari |
|---|---|---|
| `echoCancellation` | 59+ | 11+ |
| `noiseSuppression` | 67+ | not supported |
| `autoGainControl` | 67+ | not supported |
| `sampleRate` | 59+ | 11+ (listed in `getSupportedConstraints()` only from 18.6) |
| `channelCount` | 59+ | not supported ([WebKit bug 169871](https://webkit.org/b/169871)) |

(`MediaStreamTrack.applyConstraints` and `getSupportedConstraints` rows,
**[compat]**.) Unsupported constraints are silently ignored, so Carl should
check `getSupportedConstraints()` and read back `track.getSettings()`
([MDN](https://developer.mozilla.org/en-US/docs/Web/API/MediaTrackSupportedConstraints))
**[verified]**.

On iOS `echoCancellation` switches the microphone's audio unit between voice
processing and plain capture; Safari 26 fires `configurationchange` when that
mode changes ([WebKit: Safari 26 beta](https://webkit.org/blog/16993/news-from-wwdc25-web-technology-coming-this-fall-in-safari-26-beta/))
**[verified]**. That iOS noise suppression and gain control ride along with
echo cancellation as one switch is **[judgement]**; Carl should compare both
settings on real table recordings. Since Carl never plays audio, echo
cancellation has nothing to cancel and can likely be off everywhere
**[judgement]**.

### Sample rate, AudioWorklet and encoding

- AudioWorklet: Android Chrome 66+, iOS 14.5+ **[compat]**. `new
  AudioContext({sampleRate: 16000})` is supported (Chrome 74+, iOS 14.5+), so
  the browser can resample the microphone's native rate (commonly 48 kHz) to
  16 kHz for speech-to-text **[compat]**.
- On iOS a new AudioContext starts suspended until `resume()` is called from a
  user gesture such as the Start tap **[compat, note]**.
- MediaRecorder: Chrome Android 47+, iOS 14+ **[compat]**. Safari 18.4 added
  WebM with Opus ([WebKit: Safari 18.4](https://webkit.org/blog/16574/webkit-features-in-safari-18-4/))
  and Safari 26 added PCM and ALAC ([Safari 26 beta](https://webkit.org/blog/16993/news-from-wwdc25-web-technology-coming-this-fall-in-safari-26-beta/))
  **[verified]**. WebCodecs `AudioEncoder`: Chrome Android 94+, iOS 26+
  **[compat]**. So Opus can be produced in the page on both current browsers.

## Screen lock and background

- **iOS: capture stops when the page is hidden.** WebKit's
  `InterruptAudioOnPageVisibilityChangeEnabled` preference defaults to true on
  iOS, and `Document` mutes the microphone source whenever `document.hidden`
  is true ([UnifiedWebPreferences.yaml](https://github.com/WebKit/WebKit/blob/main/Source/WTF/Scripts/Preferences/UnifiedWebPreferences.yaml),
  [Document.cpp](https://github.com/WebKit/WebKit/blob/main/Source/WebCore/dom/Document.cpp),
  `source.setMuted(... || (document.hidden() && ...interruptAudioOnPageVisibilityChangeEnabled()))`)
  **[code]**. Switching tab, switching app or locking the screen therefore
  means silence. Beyond that, iOS suspends JavaScript in hidden pages, so open
  WebSockets and timers should be assumed dead after a lock **[judgement]**.
- **Android Chrome: capture continues in the background.** While a page
  captures, Chrome runs `MediaCaptureNotificationService` as an Android
  foreground service with the microphone service type, showing a "using your
  microphone" notification ([source](https://chromium.googlesource.com/chromium/src/+/main/chrome/android/java/src/org/chromium/chrome/browser/media/MediaCaptureNotificationServiceImpl.java))
  **[code]**. Chrome does not discard hidden pages that play audio or use
  WebRTC except under extreme memory pressure ([Page Lifecycle API](https://developer.chrome.com/docs/web-platform/page-lifecycle-api))
  **[verified]**, and a live `MediaStreamTrack` exempts the page from
  intensive timer throttling ([Chrome 88 timer throttling](https://developer.chrome.com/blog/timer-throttling-in-chrome-88))
  **[verified]**. Individual reports of the microphone going quiet a few
  seconds into the background exist (Chromium issue 374374232, not readable
  without sign-in), so background capture on Android is likely but not
  guaranteed **[judgement]**.
- **Screen Wake Lock** keeps the screen on while the page is visible: Android
  Chrome 84+; iOS Safari tabs 16.4+; iOS Home Screen web apps only from 18.4
  ([WebKit bug 254545](https://bugs.webkit.org/show_bug.cgi?id=254545),
  [Safari 18.4](https://webkit.org/blog/16574/webkit-features-in-safari-18-4/))
  **[compat, verified]**. The lock is released whenever the page is hidden and
  has to be requested again on `visibilitychange`.
- Lifecycle events: `visibilitychange` and `pagehide` exist on both; the
  `freeze` event is Chrome-only **[compat]**. `pagehide`/`visibilitychange` is
  the last reliable moment to save the session's cards.

## Geolocation

`watchPosition` is supported on both since the earliest versions **[compat]**.
It needs HTTPS and a permission prompt. Carl needs only a coarse "where is the
table" once per session, so a single `getCurrentPosition` at Start suffices;
no background location is available to web pages on either platform
**[judgement]**.

## Streaming to a server

- WebSocket: universal **[compat]**. `WebSocketStream` is Chrome-only
  **[compat]**.
- WebRTC (`RTCPeerConnection`): Android Chrome 56+, iOS 11+ **[compat]**.
  WebTransport: Chrome Android 97+, iOS 26.4+ **[compat]**.
- Any of these works while the page is visible. On iOS they carry nothing
  useful once the page is hidden (see above), so reconnect on return.

## Storage

### Quota

| | Per-site quota | All sites together |
|---|---|---|
| Android Chrome | up to 60% of total disk | up to 80% |
| iOS Safari (and Home Screen web apps) | up to 60% of total disk | up to 80% |

Sources: [web.dev: Storage for the web](https://web.dev/articles/storage-for-the-web),
[WebKit: Updates to Storage Policy](https://webkit.org/blog/14403/updates-to-storage-policy/)
(Safari 17+, iOS 17+), [MDN: Storage quotas and eviction criteria](https://developer.mozilla.org/en-US/docs/Web/API/Storage_API/Storage_quotas_and_eviction_criteria)
**[verified]**. WebKit warns that the quota "might change based on factors
like existing usage and site visit frequency", so a write can still fail with
`QuotaExceededError`. `navigator.storage.estimate()`: Chrome Android 61+,
iOS 17+ **[compat]**. `localStorage` is capped separately at about 5 MiB
([MDN](https://developer.mozilla.org/en-US/docs/Web/API/Storage_API/Storage_quotas_and_eviction_criteria))
**[verified]**.

**Can it hold hours of audio?** Easily, as long as the phone has free space:

| Format | Bytes per second | 1 hour | 2 hours |
|---|---|---|---|
| 16 kHz mono 16-bit PCM | 32 000 | 115 MB | 230 MB |
| 48 kHz mono 32-bit float (raw AudioWorklet output) | 192 000 | 691 MB | 1.4 GB |
| 16 kHz mono Opus at 24 kbit/s | 3 000 | 11 MB | 22 MB |

(Arithmetic, not a source.) A card archive of text is tiny by comparison.

### Where to store it

- IndexedDB: everywhere.
- OPFS (`navigator.storage.getDirectory()`): Chrome Android 109+, iOS 15.2+.
  Writing on iOS before 26 needs `createSyncAccessHandle()` inside a worker;
  `createWritable()` arrived in iOS 26 **[compat]**. OPFS suits appending
  large audio files; IndexedDB suits cards and the failure log.

### Eviction: when data disappears on its own

- **Both browsers** evict whole sites, least recently used first, when the
  overall quota is exceeded or the device is short of space. Sites in
  persistent mode are skipped ([WebKit](https://webkit.org/blog/14403/updates-to-storage-policy/),
  [web.dev](https://web.dev/articles/storage-for-the-web)) **[verified]**.
  WebKit also skips a site that has a page open at the time.
- **iOS Safari tabs: the seven-day cap.** Since iOS 13.4, Safari deletes "all
  script-writable storage" (IndexedDB, localStorage, service worker
  registrations and cache, and more) "after seven days of Safari use without
  user interaction on the site" ([WebKit: Full third-party cookie blocking
  and more](https://webkit.org/blog/10218/full-third-party-cookie-blocking-and-more/))
  **[verified]**. The clock counts days Safari is used, not calendar days, and
  any tap on Carl's site resets it. The 2023 storage policy lists "File
  System" (OPFS) among the APIs its eviction covers **[verified]**; that the
  seven-day deletion takes OPFS too is **[judgement]**.
- **iOS Home Screen web apps are exempt in practice.** "Web applications added
  to the home screen are not part of Safari and thus have their own counter of
  days of use. Their days of use will match actual use of the web
  application which resets the timer" ([WebKit](https://webkit.org/blog/10218/full-third-party-cookie-blocking-and-more/))
  **[verified]**. Since Safari 26, any site added to the Home Screen opens as a
  web app by default, with no manifest needed ([Safari 26 beta](https://webkit.org/blog/16993/news-from-wwdc25-web-technology-coming-this-fall-in-safari-26-beta/))
  **[verified]**.
- **Home Screen storage is a separate container.** "Home Screen apps are
  created as isolated entities without shared state with the browser" (Apple's
  Brent Fulgham, 2022, [WebKit bug 181849](https://bugs.webkit.org/show_bug.cgi?id=181849),
  still open) **[verified]**. Cards saved while Carl ran in a Safari tab will
  not appear in the installed app, and the reverse. Removing the Home Screen
  icon most likely deletes its data **[judgement]**.

### `navigator.storage.persist()`

- Supported on Chrome Android 55+ and iOS 15.2+ **[compat]**. Neither shows a
  prompt; each decides by heuristics ([MDN](https://developer.mozilla.org/en-US/docs/Web/API/Storage_API/Storage_quotas_and_eviction_criteria))
  **[verified]**.
- **Chrome** weighs site engagement, whether the site is installed or
  bookmarked, and whether it may show notifications; a denied request can be
  retried later ([web.dev: Persistent storage](https://web.dev/articles/persistent-storage))
  **[verified]**.
- **WebKit** "currently grants a request based on heuristics like whether the
  website is opened as a Home Screen Web App" ([WebKit](https://webkit.org/blog/14403/updates-to-storage-policy/))
  **[verified]**. Whether persistent mode also lifts the seven-day cap in a
  Safari tab is not stated; assume it does not **[judgement]**.
- Persistence protects only against automatic eviction. The owner clearing
  website data, uninstalling the app, resetting or losing the phone still
  deletes everything.

## Export and download

- `<a download href="blob:…">`: Chrome Android 18+, iOS 13+ **[compat]**. On
  iOS the file goes to the Files app's Downloads (**[judgement]** on the exact
  destination).
- Web Share with files (`navigator.share({files})`): Chrome Android 76+,
  iOS 14+ **[compat]**. Opens the system share sheet: save to Files, AirDrop,
  mail, a notes app.
- `showSaveFilePicker()`: Chrome Android 132+, not on iOS **[compat]**.
- Import back is a plain `<input type="file">`.

## Implications for Carl

Observations, not decisions.

- **Install on iOS changes the picture.** In a Safari tab the card archive can
  vanish after a week of the owner not opening Carl; as a Home Screen web app
  it only ages while used, and `persist()` is likely to be granted. On Android
  Chrome a plain tab is already fairly safe, and installing or bookmarking
  helps `persist()`. The requirement "no app install" still holds, since adding
  to the Home Screen is not an app-store install, but it is a step the owner
  has to take once, and the tab and the Home Screen app do not share data.
- **The card archive can live only on the phone with care, not with
  certainty.** Carl can call `persist()` at the first Start, show whether it
  was granted, and warn when it was not. Even then, phone loss or clearing
  site data deletes it; an occasional export (share sheet or download) is the
  cheap safety net. The failure log's 30-day expiry and the test corpus's
  6-month audio rule are unaffected by quota.
- **The screen stays on during a session.** Carl should hold a Screen Wake
  Lock for the whole session and re-request it after `visibilitychange`. On
  iOS a locked screen or a switch to another app means Carl hears nothing, so
  the listening indicator should show "can't hear" and the failure log should
  record it. On Android, background capture probably continues but should not
  be relied on.
- **Save cards as they arrive,** not at the end: `pagehide` is not
  guaranteed, and a session ends when the page is closed.
- **Recording sessions fit in storage.** Two hours of 16 kHz audio is about
  230 MB as PCM or about 22 MB as Opus, well within quota on any current
  phone; Opus can be encoded in the page on both (MediaRecorder WebM/Opus on
  iOS 18.4+, WebCodecs on iOS 26+). Moving recordings off the phone for the
  test corpus is an export step either way.
- **Microphone processing is a tuning knob on Android and a single switch on
  iOS.** Far-field quality should be compared with processing on and off on
  real table recordings before choosing defaults; the page should read back
  `getSettings()` to know what it actually got.
- **Minimum versions** implied by the above: iOS 18.4 for wake lock in a Home
  Screen web app and WebM/Opus recording; Android Chrome is not a constraint.

## Sources

WebKit (Apple):

- Updates to Storage Policy (2023): https://webkit.org/blog/14403/updates-to-storage-policy/
- Full Third-Party Cookie Blocking and More (2020, seven-day cap): https://webkit.org/blog/10218/full-third-party-cookie-blocking-and-more/
- A Closer Look Into WebRTC: https://webkit.org/blog/7763/a-closer-look-into-webrtc/
- WebKit Features in Safari 16.4: https://webkit.org/blog/13966/webkit-features-in-safari-16-4/
- WebKit Features in Safari 18.4: https://webkit.org/blog/16574/webkit-features-in-safari-18-4/
- Safari 26 beta (WWDC25): https://webkit.org/blog/16993/news-from-wwdc25-web-technology-coming-this-fall-in-safari-26-beta/
- Bugs: 185448 (getUserMedia in standalone) https://bugs.webkit.org/show_bug.cgi?id=185448 ;
  212040 https://bugs.webkit.org/show_bug.cgi?id=212040 ;
  181849 (separate storage) https://bugs.webkit.org/show_bug.cgi?id=181849 ;
  254545 (wake lock in Home Screen apps) https://bugs.webkit.org/show_bug.cgi?id=254545 ;
  169871 (channelCount) https://webkit.org/b/169871
- Source: `Source/WTF/Scripts/Preferences/UnifiedWebPreferences.yaml` and
  `Source/WebCore/dom/Document.cpp`, https://github.com/WebKit/WebKit (main,
  2026-09-25)

Chrome (Google):

- Page Lifecycle API: https://developer.chrome.com/docs/web-platform/page-lifecycle-api
- Timer throttling in Chrome 88: https://developer.chrome.com/blog/timer-throttling-in-chrome-88
- Storage for the web: https://web.dev/articles/storage-for-the-web
- Persistent storage: https://web.dev/articles/persistent-storage
- Source: `chrome/android/java/src/org/chromium/chrome/browser/media/MediaCaptureNotificationServiceImpl.java`,
  https://chromium.googlesource.com/chromium/src/ (main, 2026-09-25)

MDN:

- Storage quotas and eviction criteria: https://developer.mozilla.org/en-US/docs/Web/API/Storage_API/Storage_quotas_and_eviction_criteria
- MediaTrackSupportedConstraints: https://developer.mozilla.org/en-US/docs/Web/API/MediaTrackSupportedConstraints
- Browser compatibility data 8.1.3: https://github.com/mdn/browser-compat-data
  (read via https://cdn.jsdelivr.net/npm/@mdn/browser-compat-data/data.json)
