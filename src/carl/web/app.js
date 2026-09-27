// Carl's page (spec section 8): the Start screen, the recording disclosure,
// the session screen and the "Session ended" summary. The server holds the
// session: the page opens the microphone and the location watch, sends the
// taps and shows what the server says. The cards are paced in cards.js. The
// messages are in docs/websocket.md.

import {Cards} from "./cards.js";
import {Geo} from "./geo.js";
import {Link} from "./link.js";
import {Mic} from "./mic.js";

// The disclosure, word for word (spec section 9, The disclosure text). With
// Location off, the location clause is left out.
const disclosureFi = (withLocation) => `Tämä on testi. Carl tallentaa keskustelun äänen ja tekstin${withLocation ? " sekä puhelimen sijainnin" : ""}. Ääni ja raakalokit poistuvat 6 kuukauden kuluttua; korjattu teksti ilman nimiä säilyy siihen asti, kunnes poistan sen. Vain minä ja testattavat tekoälypalvelut käsittelevät niitä. Kuka tahansa voi pyytää lopettamaan tallennuksen.`;
const disclosureEn = (withLocation) => `This is a test. Carl records the conversation's audio and text${withLocation ? " and the phone's location" : ""}. Audio and raw logs are deleted after 6 months; the corrected text, without names, stays until I delete it. Only I and the AI services being tested handle them. Anyone can ask to stop the recording.`;

const PULSE_MS = 1500;  // the dot pulses this long after each `speech`
const STOPS_KEY = "carl.pendingStops";  // stops the server hasn't confirmed yet
const LOCATION_KEY = "carl.location";  // the Location switch, "on" or "off"
const INDICATOR = {
  starting: "Starting…",
  listening: "Listening",
  paused: "Paused",
  dropped: "Connection lost, reconnecting…",  // "Can't hear" comes with step 7
};
const RECORDING = {kept: "Kept", stopped: "Stopped and deleted"};

const $ = (id) => document.getElementById(id);
const link = new Link(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/api/ws`);
const mic = new Mic();
// Location messages go only to a session the server has confirmed.
const geo = new Geo((message) => !session?.over && confirmedSend(message), () => link.config.location);
// The cards' reports wait, in order, for the session to be confirmed again.
const cards = new Cards({
  current: $("current"), history: $("history"),
  report: (message) => { reports.push(message); sendReports(); },
  config: () => link.config?.screen,
});

let screen = "start";  // start, disclosure, session or ended
let recordOn = false;  // off by default every time, never remembered
let locationOn = savedLocation();  // on the first time, then remembered on this phone
let monthEur = null;
let everConnected = false;
let micRefused = false;
let endAsk = false;
// The running or just-ended session. `state` and `recording` are the
// server's; `paused` and `stopped` are this page's taps, which win.
let session = null;
let reports = [];  // card_shown and card_filed not sent yet

// ---- the taps ----

$("record").onclick = () => { recordOn = !recordOn; render(); };
$("location").onclick = () => { locationOn = !locationOn; saveLocation(); render(); };
$("start-button").onclick = () => {
  if (recordOn) { screen = "disclosure"; render(); } else begin(false, null);
};
$("back").onclick = () => { screen = "start"; render(); };
$("agree").onclick = () => begin(true, {  // exactly the text shown
  text: `${$("disclosure-fi").textContent}\n\n${$("disclosure-en").textContent}`,
  confirmed_at: new Date().toISOString(),
});
$("no-record").onclick = () => begin(false, null);
$("pause").onclick = () => togglePause();
$("end").onclick = () => { endAsk = true; render(); };
$("end-cancel").onclick = () => { endAsk = false; render(); };
$("end-yes").onclick = () => { endAsk = false; end(); };
$("rec-mark").onclick = () => $("stop").showModal();
$("stop-no").onclick = () => $("stop").close();
$("stop-yes").onclick = () => { $("stop").close(); stopRecording(); };
$("stop").onclick = (e) => { if (e.target === $("stop")) $("stop").close(); };  // the backdrop
$("to-start").onclick = () => { session = null; recordOn = false; screen = "start"; render(); };

// Start, from the Start screen or the disclosure. The microphone opens first,
// straight from the tap, and `start` goes once it is open.
async function begin(record, disclosure) {
  if (session && !session.over) return;
  const s = session = {
    id: null, start: null, state: null, recording: false, record, location: locationOn,
    paused: false, stopped: false, opening: true, rejoining: false,
    over: false, summary: null,
  };
  const opening = mic.open();  // before any await, while the tap still counts
  geo.reset();
  micRefused = endAsk = false;
  reports = [];
  cards.reset();
  screen = "session";
  holdWakeLock();
  render();
  let settings;
  try {
    settings = await opening;
  } catch (e) {
    if (s !== session || s.over) return;  // ended while it opened
    // Refused or missing: nothing was sent, so back to the Start screen.
    console.warn("microphone:", e);
    mic.shutdown();
    dropWakeLock();
    session = null; micRefused = true; screen = "start";
    render();
    return;
  } finally {
    s.opening = false;
  }
  if (s !== session || s.over) return;
  s.start = {
    type: "start", record, disclosure, mic: settings, location: s.location,
    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
    start_id: crypto.randomUUID(),  // a resent start carries on the same session
  };
  link.send(s.start);
  if (s.location) geo.start();  // after the microphone, so the phone asks one thing at a time
  render();
}

async function togglePause() {
  const s = session;
  if (!s || s.over || s.opening) return;
  if (!s.paused) {
    s.paused = true;
    mic.close();
    geo.stop();
    link.send({type: "pause"});
    render();
    return;
  }
  s.opening = true;
  render();
  try {
    await mic.open();
  } catch (e) {
    console.warn("microphone:", e);  // stays paused; another tap tries again
    return;
  } finally {
    s.opening = false;
    render();
  }
  if (s !== session || s.over) return;
  s.paused = false;
  link.send({type: "resume"});
  if (s.location) geo.start();
  render();
}

// End, confirmed in the top bar or on pagehide. The summary follows in
// `ended`. If the connection is down, the next hello rejoins and ends it then.
function end() {
  const s = session;
  if (!s || s.over) return;
  s.over = true;
  release();
  if (!s.start) {  // the microphone was still opening: nothing started
    session = null; screen = "start";
    render();
    return;
  }
  // Without an id there is nothing to rejoin, so no summary will come.
  sendReports();
  if (!link.send({type: "end"}) && !s.id) s.summary = {};
  screen = "ended";
  render();
}

function release() {
  cards.stop();
  mic.shutdown();
  geo.stop();
  dropWakeLock();
  if ($("stop").open) $("stop").close();
}

// "Stop recording?" confirmed: the mark goes at once and for good, and the
// stop is kept until the server confirms it, across reloads too.
function stopRecording() {
  const s = session;
  if (!s || s.stopped || !s.id) return;
  s.stopped = true;
  savePendingStops([...new Set([...pendingStops(), s.id])]);
  link.send({type: "stop_recording", session: s.id});
  render();
}

function savedLocation() {
  try { return localStorage.getItem(LOCATION_KEY) !== "off"; } catch { return true; }
}

function saveLocation() {
  try { localStorage.setItem(LOCATION_KEY, locationOn ? "on" : "off"); } catch { /* not kept past this page */ }
}

function pendingStops() {
  try { return JSON.parse(localStorage.getItem(STOPS_KEY)) ?? []; } catch { return []; }
}

function savePendingStops(ids) {
  try {
    if (ids.length) localStorage.setItem(STOPS_KEY, JSON.stringify(ids));
    else localStorage.removeItem(STOPS_KEY);
  } catch { /* storage refused: the stop still went if the link was up */ }
}

// ---- the server ----

// Sends a message that belongs to the session, once the server has
// confirmed it on this connection. False if it couldn't go yet.
function confirmedSend(message) {
  const s = session;
  return !!s?.id && !s.rejoining && link.state === "connected" && link.send(message);
}

function sendReports() {
  while (reports.length && confirmedSend(reports[0])) reports.shift();
}

// Each hello: pending stops first, so a rejoin already sees them, then carry
// on with the session, or finish ending it if the connection dropped before
// its summary came.
link.addEventListener("state", ({detail}) => {
  if (detail === "connected") {
    everConnected = true;
    monthEur = link.costs?.month_eur ?? null;
    for (const id of pendingStops()) link.send({type: "stop_recording", session: id});
    const s = session;
    if (s && !s.over && s.id) {
      s.rejoining = true;
      link.send({type: "rejoin", session: s.id});
    } else if (s && !s.over && s.start) {
      link.send(s.start);  // no answer to `start` came before the drop
    } else if (s?.over && !s.summary && s.id) {
      s.rejoining = true;
      link.send({type: "rejoin", session: s.id});
    }
  }
  render();
});

link.addEventListener("message", ({detail: m}) => {
  if (m.type === "session") onSession(m);
  else if (m.type === "speech") pulse();
  else if (m.type === "card") { if (session?.id && !session.over) cards.add(m.card); }
  else if (m.type === "cards") { if (session?.id && !session.over) cards.restore(m); }
  else if (m.type === "ended") onEnded(m);
  else if (m.type === "recording_stopped") {
    savePendingStops(pendingStops().filter((id) => id !== m.session));
  }
});

function onSession(m) {
  const s = session;
  if (!s || (s.id && m.session !== s.id)) return;
  s.id = m.session;
  if (s.over) {
    // Ended here while the connection was down: the rejoin found it running.
    if (s.rejoining) { s.rejoining = false; sendReports(); link.send({type: "end"}); }
    return;
  }
  s.state = m.state;
  s.recording = m.recording;
  if (s.rejoining) {
    // Taps made while the connection was down win.
    s.rejoining = false;
    if (s.paused && m.state === "listening") link.send({type: "pause"});
    else if (!s.paused && m.state === "paused" && mic.live) link.send({type: "resume"});
  }
  geo.flush();  // a fix or denial that came while the session wasn't confirmed
  sendReports();  // cards shown or filed while the connection was down
  render();
}

function onEnded(m) {
  if (m.summary?.month_eur != null) monthEur = m.summary.month_eur;
  const s = session;
  if (s?.id && m.session === s.id) {
    if (!s.over) { s.over = true; endAsk = false; release(); screen = "ended"; }
    s.rejoining = false;
    s.summary = m.summary ?? {};
    reports = [];
  }
  render();
}

// Audio goes only while the server says the session is listening.
mic.onchunk = (chunk) => {
  const s = session;
  if (s && !s.over && !s.paused && !s.rejoining && s.state === "listening") link.sendAudio(chunk);
};

let pulseTimer = 0;
function pulse() {
  $("indicator").classList.add("speaking");
  clearTimeout(pulseTimer);
  pulseTimer = setTimeout(() => $("indicator").classList.remove("speaking"), PULSE_MS);
}

// ---- the screen kept on, and the page going away ----

let wakeLock = null, wakeLockAsked = false;
async function holdWakeLock() {
  if (wakeLock || wakeLockAsked || !navigator.wakeLock || document.visibilityState !== "visible") return;
  wakeLockAsked = true;
  try {
    const lock = await navigator.wakeLock.request("screen");
    if (session && !session.over) {
      wakeLock = lock;
      lock.addEventListener("release", () => { if (wakeLock === lock) wakeLock = null; });
    } else lock.release();
  } catch (e) {
    console.warn("wake lock:", e);  // step 7 logs it; the session carries on
  } finally {
    wakeLockAsked = false;
  }
}

function dropWakeLock() {
  wakeLock?.release().catch(() => {});
  wakeLock = null;
}

document.addEventListener("visibilitychange", () => {
  if (session && !session.over) holdWakeLock();
});
addEventListener("pagehide", () => end());

// ---- drawing ----

function render() {
  for (const id of ["start", "disclosure", "session", "ended"]) $(id).hidden = screen !== id;
  const connected = link.state === "connected";
  const down = everConnected ? "Connection lost, reconnecting…" : "Connecting…";

  // Start and disclosure
  $("start-button").disabled = !connected;
  $("agree").disabled = $("no-record").disabled = !connected;
  $("record").setAttribute("aria-checked", String(recordOn));
  $("location").setAttribute("aria-checked", String(locationOn));
  $("disclosure-fi").textContent = disclosureFi(locationOn);
  $("disclosure-en").textContent = disclosureEn(locationOn);
  $("month").hidden = monthEur == null;
  if (monthEur != null) $("month-eur").textContent = `≈ ${euros(monthEur)}`;
  const note = !connected ? down : micRefused ? "Carl couldn't open the microphone." : "";
  $("start-note").textContent = note;
  $("start-note").hidden = !note;
  $("start-note").classList.toggle("problem", micRefused && connected);
  $("disclosure-note").textContent = connected ? "" : down;
  $("disclosure-note").hidden = connected;

  // Session
  const s = session;
  if (screen === "session" && s) {
    const state = !connected || s.rejoining ? "dropped"
      : s.paused || s.state === "paused" ? "paused"
      : s.state === "listening" ? "listening" : "starting";
    $("indicator").dataset.state = state;
    $("indicator-text").textContent = INDICATOR[state];
    $("rec-mark").hidden = state === "dropped" || !s.recording || s.paused || s.stopped;
    if ($("rec-mark").hidden && $("stop").open) $("stop").close();
    $("pause").textContent = s.paused ? "Resume" : "Pause";
    $("pause").classList.toggle("on", s.paused);
    $("pause").disabled = s.opening;
    $("bar").hidden = endAsk;
    $("end-ask").hidden = !endAsk;
  }

  // Session ended
  if (screen === "ended" && s) {
    const sum = s.summary, waiting = "…";
    $("sum-listening").textContent = sum ? duration(sum.listening_s) : waiting;
    $("sum-cards").textContent = !sum ? waiting : sum.cards == null ? "—" : String(sum.cards);
    $("sum-cost").textContent = !sum ? waiting : sum.cost_eur == null ? "—" : `≈ ${euros(sum.cost_eur)}`;
    const recording = s.stopped ? "stopped" : sum?.recording ?? (s.record ? null : "none");
    $("sum-recording-row").hidden = recording === "none";
    $("sum-recording").textContent = RECORDING[recording] ?? waiting;
  }
}

function euros(x) {
  return `€${x.toFixed(2)}`;
}

function duration(seconds) {
  if (seconds == null) return "—";
  if (seconds < 60) return `${Math.round(seconds)} s`;
  const minutes = Math.round(seconds / 60);
  return minutes < 60 ? `${minutes} min` : `${Math.floor(minutes / 60)} h ${minutes % 60} min`;
}

render();
link.connect();
