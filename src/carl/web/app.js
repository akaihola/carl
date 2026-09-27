// Carl's page (spec section 8): the Start screen, the recording disclosure,
// the session screen and the "Session ended" summary. The server holds the
// session: the page opens the microphone and the location watch, sends the
// taps and shows what the server says. The cards are paced in cards.js. The
// messages are in docs/websocket.md.
//
// The listening indicator (spec section 10): the server's "Can't hear" or
// "Can't check", and the page's own "Can't hear" when the connection is
// down, the microphone is lost or the page is hidden. What only the page
// sees goes into its buffer of page events, sent once the server can take
// them: at once while connected, else after the rejoin.

import {Cards} from "./cards.js";
import {Geo} from "./geo.js";
import {Link} from "./link.js";
import {Mic} from "./mic.js";

// The disclosure, word for word (spec section 9, The disclosure text). With
// Location off, the location clause is left out.
const disclosureFi = (withLocation) => `Tämä on testi. Carl tallentaa keskustelun äänen ja tekstin${withLocation ? " sekä puhelimen sijainnin" : ""}. Ääni ja raakalokit poistuvat 6 kuukauden kuluttua; korjattu teksti ilman nimiä säilyy siihen asti, kunnes poistan sen. Vain minä ja testattavat tekoälypalvelut käsittelevät niitä. Kuka tahansa voi pyytää lopettamaan tallennuksen.`;
const disclosureEn = (withLocation) => `This is a test. Carl records the conversation's audio and text${withLocation ? " and the phone's location" : ""}. Audio and raw logs are deleted after 6 months; the corrected text, without names, stays until I delete it. Only I and the AI services being tested handle them. Anyone can ask to stop the recording.`;

const PULSE_MS = 1500;  // the dot pulses this long after each `speech`
const MIC_RETRY_MS = 5000;  // an ended microphone is tried again this often
const MIC_OPEN_MS = 8000;  // a reopen that hasn't finished by then has failed
const STOPS_KEY = "carl.pendingStops";  // stops the server hasn't confirmed yet
const LOCATION_KEY = "carl.location";  // the Location switch, "on" or "off"
const INDICATOR = {
  starting: "Starting…",
  listening: "Listening",
  paused: "Paused",
  cant_hear: "Can't hear",
  cant_check: "Can't check",
};
const PROBLEMS = new Set(["cant_hear", "cant_check"]);
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
  failed: (id) => note({kind: "card-render-failed", at: now(), id}),
  config: () => link.config?.screen,
});
// The handover waits while a start or a rejoin is on its way.
link.canHandover = () => !session || session.over || (!!session.id && !session.rejoining);

let screen = "start";  // start, disclosure, session or ended
let recordOn = false;  // off by default every time, never remembered
let locationOn = savedLocation();  // on the first time, then remembered on this phone
let monthEur = null;
// The Start screen's last-session line: from each hello, and from the
// summary of a session that just ended here.
let lastSession = null;
let everConnected = false;
let micRefused = false;
let endAsk = false;
// The running or just-ended session. `state` and `recording` are the
// server's; `paused` and `stopped` are this page's taps, which win.
let session = null;
let reports = [];  // card_shown and card_filed not sent yet
// The page's buffer (spec section 10, What the page buffers), and the
// stretches still open.
let events = [];  // page_events not sent yet
let gapStart = null;  // the connection dropped during the session
let hiddenStart = null;  // the page hidden during the session
let micLost = null;  // {detail, start} while the microphone is lost
let micTold = null;  // the last `mic` state the server heard: "lost" or "back"
let micRetry = 0, micOpening = false;

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
    paused: false, stopped: false, opening: true, rejoining: false, handover: false,
    problem: null, over: false, summary: null,
  };
  const opening = mic.open();  // before any await, while the tap still counts
  geo.reset();
  micRefused = endAsk = false;
  reports = [];
  events = [];
  gapStart = hiddenStart = micLost = micTold = null;
  clearTimeout(micRetry);
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
  s.startedAt = new Date().toISOString();
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
  micBack();  // a microphone lost before the pause is open again
  if (mic.muted) mic.onlost("muted");
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
  closeStretches();
  sendEvents();
  sendReports();
  if (!link.send({type: "end"}) && !s.id) s.summary = {};
  screen = "ended";
  render();
}

function release() {
  clearTimeout(micRetry);
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

const now = () => new Date().toISOString();

// A page event: into the buffer, and to the server if it can take it now.
function note(event) {
  events.push(event);
  sendEvents();
}

function sendEvents() {
  if (events.length && confirmedSend({type: "page_events", events})) events = [];
}

// The connection gap ends when the server has the session again.
function closeGap() {
  if (gapStart) events.push({kind: "gap", start: gapStart, end: now()});
  gapStart = null;
}

// At End, whatever is still open ends too.
function closeStretches() {
  const t = now();
  if (hiddenStart) events.push({kind: "hidden", start: hiddenStart, end: t});
  if (micLost) events.push({kind: "mic-lost", start: micLost.start, end: t, detail: micLost.detail});
  hiddenStart = micLost = null;
}

// The server hears the microphone's state live when it can; after a rejoin
// it hears it again.
function tellMic() {
  if (micLost && micTold !== "lost") {
    if (confirmedSend({type: "mic", state: "lost", detail: micLost.detail})) micTold = "lost";
  } else if (!micLost && micTold === "lost") {
    if (confirmedSend({type: "mic", state: "back"})) micTold = "back";
  }
}

// Each hello: pending stops first, so a rejoin already sees them, then carry
// on with the session, or finish ending it if the connection dropped before
// its summary came.
link.addEventListener("state", ({detail}) => {
  const s = session;
  if (detail === "dropped" && s) {
    s.handover = false;
    if (!s.summary && (s.id || s.start)) gapStart ??= now();
  }
  if (detail === "connected") {
    everConnected = true;
    fromHello();
    for (const id of pendingStops()) link.send({type: "stop_recording", session: id});
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

// The handover's second socket said hello: it rejoins the session, or just
// takes over when there is none.
link.addEventListener("handover", () => {
  const s = session;
  if (s && !s.over && (!s.id || s.rejoining)) link.abortHandover();
  else if (s?.id && !s.summary && link.sendNext({type: "rejoin", session: s.id})) s.handover = true;
  else { link.switchover(); fromHello(); render(); }
});

// The costs on the Start screen, as the latest hello has them.
function fromHello() {
  monthEur = link.costs?.month_eur ?? null;
  lastSession = link.costs?.last_session ?? null;
}

// The answer to the handover's rejoin, on the second socket: it takes over.
function tookOver(s, handover) {
  if (!handover || !s?.handover) return false;
  s.handover = false;
  link.switchover();
  fromHello();
  for (const id of pendingStops()) link.send({type: "stop_recording", session: id});
  return true;
}

link.addEventListener("message", ({detail: m, handover}) => {
  if (m.type === "session") onSession(m, handover);
  else if (m.type === "indicator") onIndicator(m);
  else if (m.type === "speech") pulse();
  else if (m.type === "card") { if (session?.id && !session.over) cards.add(m.card); }
  else if (m.type === "cards") { if (session?.id && !session.over) cards.restore(m); }
  else if (m.type === "card_withdrawn") { if (session?.id && !session.over) cards.withdraw(m.id); }
  else if (m.type === "ended") onEnded(m, handover);
  else if (m.type === "recording_stopped") {
    savePendingStops(pendingStops().filter((id) => id !== m.session));
  }
});

function onSession(m, handover) {
  const s = session;
  if (!s || (s.id && m.session !== s.id)) return;
  const back = tookOver(s, handover) || s.rejoining;
  s.id = m.session;
  if (s.over) {
    // Ended here while the connection was down: the rejoin found it running.
    if (back) { s.rejoining = false; closeGap(); sendEvents(); sendReports(); link.send({type: "end"}); }
    return;
  }
  s.state = m.state;
  s.recording = m.recording;
  if (back) {
    // Taps made while the connection was down, or during the handover, win.
    s.rejoining = false;
    if (s.paused && m.state === "listening") link.send({type: "pause"});
    else if (!s.paused && m.state === "paused" && mic.live) link.send({type: "resume"});
    if (micLost) micTold = null;  // said again, in case the server lost it
  }
  closeGap();
  geo.flush();  // a fix or denial that came while the session wasn't confirmed
  sendReports();  // cards shown or filed while the connection was down
  tellMic();
  sendEvents();
  render();
}

function onEnded(m, handover) {
  if (m.summary?.month_eur != null) monthEur = m.summary.month_eur;
  const s = session;
  tookOver(s, handover);
  if (s?.id && m.session === s.id) {
    if (!s.over) { s.over = true; endAsk = false; release(); screen = "ended"; }
    s.rejoining = false;
    s.summary = m.summary ?? {};
    lastSession = justEnded(s, s.summary);
    reports = [];
    events = [];
    gapStart = hiddenStart = micLost = null;
  }
  render();
}

// The session that just ended is the last session now. The hello has the
// server's own line, with €/h, from the next connection on; until then the
// summary's figures stand in, without €/h.
function justEnded(s, sum) {
  if (sum.last_session !== undefined) return sum.last_session;
  if (sum.listening_s == null || !s.startedAt) return lastSession;
  return {started: s.startedAt, timezone: s.start.timezone, listening_s: sum.listening_s, cost_eur: sum.cost_eur ?? null, eur_per_hour: null};
}

// The server's side of the indicator. Its reason code is for the log only.
function onIndicator(m) {
  const s = session;
  if (!s || s.over) return;
  s.problem = PROBLEMS.has(m.problem) ? m.problem : null;
  render();
}

// Audio goes only while the server says the session is listening.
mic.onchunk = (chunk) => {
  const s = session;
  if (s && !s.over && !s.paused && !s.rejoining && s.state === "listening") link.sendAudio(chunk);
};

// ---- the microphone lost ----

// Its track ended or was muted, or the permission was revoked (spec section
// 10, Can't hear). Paused, the microphone is closed on purpose.
mic.onlost = (detail) => {
  const s = session;
  if (!s || s.over || s.paused) return;
  if (micLost) {
    if (detail === "permission" && micLost.detail !== detail) { micLost.detail = detail; micTold = null; tellMic(); }
    return;
  }
  micLost = {detail, start: now()};
  tellMic();
  render();
  if (detail !== "muted") reopenSoon(0);
};
mic.onback = () => micBack();  // unmuted
mic.ongranted = () => { if (micLost && micLost.detail !== "muted") reopenSoon(0); };

function micBack() {
  if (!micLost) return;
  note({kind: "mic-lost", start: micLost.start, end: now(), detail: micLost.detail});
  micLost = null;
  clearTimeout(micRetry);
  tellMic();
  render();
}

function reopenSoon(ms) {
  clearTimeout(micRetry);
  micRetry = setTimeout(reopenMic, ms);
}

// An ended track is replaced by opening the microphone again, while the page
// is visible and the permission isn't denied (a grant brings it back).
async function reopenMic() {
  const s = session;
  if (!micLost || micLost.detail === "muted" || micOpening || !s || s.over || s.paused || s.opening) return;
  if (document.visibilityState !== "visible" || mic.permission === "denied") return;
  micOpening = true;
  let opened = false;
  try {
    await Promise.race([mic.open(), new Promise((_, no) => setTimeout(() => no(new Error("timed out")), MIC_OPEN_MS))]);
    opened = true;
  } catch (e) {
    console.warn("microphone:", e);
  } finally {
    micOpening = false;
  }
  if (s !== session || s.over) return;
  if (s.paused) { if (opened) mic.close(); return; }  // paused meanwhile
  if (!opened) {
    if (mic.permission !== "prompt") reopenSoon(MIC_RETRY_MS);
    return;
  }
  micBack();
  if (mic.muted) mic.onlost("muted");
}

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
      // Released by the browser, as when the page is hidden; asked for again
      // when it is visible.
      lock.addEventListener("release", () => {
        if (wakeLock !== lock) return;
        wakeLock = null;
        if (session && !session.over) note({kind: "wake-lock", at: now(), state: "released"});
      });
    } else lock.release();
  } catch (e) {
    console.warn("wake lock:", e);  // the session carries on
    if (session && !session.over) note({kind: "wake-lock", at: now(), state: "refused"});
  } finally {
    wakeLockAsked = false;
  }
}

function dropWakeLock() {
  const lock = wakeLock;
  wakeLock = null;  // first, so its release isn't noted
  lock?.release().catch(() => {});
}

// The page hidden is "Can't hear" (spec section 10), and a page event.
document.addEventListener("visibilitychange", () => {
  const s = session;
  if (s && !s.over) {
    if (document.visibilityState !== "visible") hiddenStart ??= now();
    else {
      if (hiddenStart) note({kind: "hidden", start: hiddenStart, end: now()});
      hiddenStart = null;
      holdWakeLock();
      if (micLost && micLost.detail !== "muted") reopenSoon(0);
    }
  }
  render();
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
  const last = lastLine(lastSession);
  $("last").hidden = !last;
  $("last").replaceChildren(...(last ?? []));
  const note = !connected ? down : micRefused ? "Carl couldn't open the microphone." : "";
  $("start-note").textContent = note;
  $("start-note").hidden = !note;
  $("start-note").classList.toggle("problem", micRefused && connected);
  $("disclosure-note").textContent = connected ? "" : down;
  $("disclosure-note").hidden = connected;

  // Session
  const s = session;
  if (screen === "session" && s) {
    // The connection down wins over Pause; Pause over everything else; the
    // page's own "Can't hear" and the server's over its "Can't check".
    const unheard = !!micLost || document.visibilityState !== "visible";
    const state = !connected || s.rejoining ? "cant_hear"
      : s.paused || s.state === "paused" ? "paused"
      : s.state !== "listening" ? "starting"
      : unheard || s.problem === "cant_hear" ? "cant_hear"
      : s.problem === "cant_check" ? "cant_check" : "listening";
    $("indicator").dataset.state = state;
    $("indicator-text").textContent = INDICATOR[state];
    // The server says whether audio is written; the page knows when none reaches it.
    $("rec-mark").hidden = !connected || s.rejoining || !!micLost || !s.recording || s.paused || s.stopped;
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
  const minutes = Math.round(seconds / 60), hours = Math.floor(minutes / 60);
  return minutes < 60 ? `${minutes} min` : minutes % 60 ? `${hours} h ${minutes % 60} min` : `${hours} h`;
}

// "Last session: Sun 27 Sep, 1 h 30 min, ≈ €0.46 (≈ €0.31/h)", as nodes;
// the parts that are unknown are left out, and null leaves the line out.
// Each part keeps together; the line breaks only between them.
function lastLine(x) {
  if (!x || typeof x !== "object") return null;
  const together = (text) => text.replaceAll(" ", "\u00a0");
  const parts = [day(x.started, x.timezone), typeof x.listening_s === "number" ? duration(x.listening_s) : null].filter(Boolean).map(together);
  const cost = typeof x.cost_eur === "number" ? together(`≈ ${euros(x.cost_eur)}`) : null;
  if (!parts.length && !cost) return null;
  const nodes = [`Last session: ${parts.join(", ")}${parts.length && cost ? ", " : ""}`];
  if (cost) {
    const b = document.createElement("b");
    b.textContent = cost;
    nodes.push(b);
  }
  if (cost && typeof x.eur_per_hour === "number") nodes.push(" " + together(`(≈ ${euros(x.eur_per_hour)}/h)`));
  return nodes;
}

// The session's date where it was held, as "Sun 27 Sep", put together from
// its parts, since browsers' own day-month forms differ.
function day(iso, timezone) {
  const date = new Date(iso ?? "");
  if (isNaN(date)) return null;
  const options = {weekday: "short", day: "numeric", month: "short"};
  let format;
  try {
    format = new Intl.DateTimeFormat("en-US", {...options, timeZone: timezone || undefined});
  } catch {
    format = new Intl.DateTimeFormat("en-US", options);  // a timezone this browser doesn't know
  }
  const part = Object.fromEntries(format.formatToParts(date).map((p) => [p.type, p.value]));
  return `${part.weekday} ${part.day} ${part.month}`;
}

render();
link.connect();
