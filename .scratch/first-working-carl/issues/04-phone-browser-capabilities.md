# What a phone browser allows a web page to do

Type: research
Status: resolved
Blocked by: 

## Question

What do current iOS Safari and Android Chrome let a plain web page (no install) do for Carl: microphone capture (getUserMedia, AudioWorklet, sample rates, echo cancellation and noise suppression settings), what happens when the screen locks or the tab is backgrounded, the Screen Wake Lock API, geolocation updates, WebSocket/WebRTC streaming, and above all **storage**: how long IndexedDB/OPFS data survives (eviction rules, Safari's 7-day limit, `navigator.storage.persist()`, home-screen web apps), and how much it can hold (hours of audio). Findings go in `docs/research/phone-browser-capabilities.md`.

## Answer

See [docs/research/phone-browser-capabilities.md](../../../docs/research/phone-browser-capabilities.md).

- Microphone capture (getUserMedia, AudioWorklet, 16 kHz AudioContext) works in iOS Safari tabs, iOS Home Screen web apps and Android Chrome without install. Android lets the page switch echo cancellation, noise suppression and gain control separately; iOS exposes only `echoCancellation`.
- iOS mutes the microphone whenever the page is hidden (other tab, other app, screen locked); Android Chrome keeps capturing in the background behind a microphone notification, probably but not guaranteed.
- Screen Wake Lock works on Android Chrome and iOS (Home Screen web apps only from iOS 18.4), so a session should hold it throughout.
- Quota is no issue: up to 60% of disk per site on both. Two hours of 16 kHz mono audio is about 230 MB as PCM, about 22 MB as Opus; Opus can be encoded in the page on both.
- In an iOS Safari tab, all script-writable storage is deleted after seven days of Safari use without interaction with the site. Home Screen web apps have their own counter that only runs while used, and WebKit grants `persist()` mainly to them. Their storage is separate from Safari's.
- Android Chrome evicts only under storage pressure; `persist()` is granted by engagement, install or bookmark.
- Export works on both through a Blob download link and the share sheet (Web Share with files); Android Chrome also has `showSaveFilePicker`.
- Implication: the card archive can live only on the phone if Carl runs as a Home Screen web app on iOS, requests `persist()` and offers occasional export; it is never safe against phone loss or cleared site data.
