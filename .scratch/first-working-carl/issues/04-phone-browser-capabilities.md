# What a phone browser allows a web page to do

Type: research
Status: claimed
Blocked by: 

## Question

What do current iOS Safari and Android Chrome let a plain web page (no install) do for Carl: microphone capture (getUserMedia, AudioWorklet, sample rates, echo cancellation and noise suppression settings), what happens when the screen locks or the tab is backgrounded, the Screen Wake Lock API, geolocation updates, WebSocket/WebRTC streaming, and above all **storage**: how long IndexedDB/OPFS data survives (eviction rules, Safari's 7-day limit, `navigator.storage.persist()`, home-screen web apps), and how much it can hold (hours of audio). Findings go in `docs/research/phone-browser-capabilities.md`.
