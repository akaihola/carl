// The cards on the session screen (spec section 8, The session screen and
// Pacing and late cards): the current card, "+N waiting" with its shrinking
// bar, and the card history. The server holds each card's state and sends it
// with its utterance time; the page paces the cards, since the taps happen
// here, and reports each card shown or filed. The messages are in
// docs/websocket.md.
//
// - With no other card waiting, the card on screen stays until someone taps
//   it away.
// - With another card waiting, it stays at least min_on_screen_s and then
//   gives way; a tap moves on at once.
// - Waiting cards go up in utterance order.
// - A card that can't reach the screen within late_card_s of its utterance,
//   measured when it would reach the screen, is a late card: it goes straight
//   into the card history, at its place by utterance time, with no mark.
//
// Everything a card shows is set as text, never as markup, and only an
// http(s) source becomes a link.

const TAP_GUARD_MS = 500;  // a tap this soon after a card came up was meant for the one before
const MIN_FIT = 0.3;  // the smallest type scale tried before a long fact scrolls instead
const DEFAULTS = {min_on_screen_s: 8, late_card_s: 20};
const RANK = {waiting: 0, current: 1, filed: 2, failed: 3};  // a card only moves forward

export class Cards {
  #current; #list; #empty; #report; #config;
  #cards = new Map();  // id -> {card, state, seq, shownAt, el}
  #seq = 0;
  #timer = 0;
  #running = false;
  #shownId = null;
  #historyKey = "";
  // Cards that failed to render, kept for the page's failure buffer (build
  // step 7 sends them on reconnect).
  failures = [];

  // `current` is the current card's region, `history` the card history.
  // `report(message)` takes each card_shown and card_filed, and `config()`
  // gives the hello's screen settings.
  constructor({current, history, report, config}) {
    this.#current = current;
    this.#list = history.querySelector(".entries");
    this.#empty = history.querySelector(".empty");
    this.#report = report;
    this.#config = config;
    current.addEventListener("click", (e) => { if (!e.target.closest("a")) this.#tap(); });
    current.addEventListener("keydown", (e) => {
      if ((e.key === "Enter" || e.key === " ") && !e.target.closest("a")) { e.preventDefault(); this.#tap(); }
    });
    new ResizeObserver(() => this.#fit()).observe(current);
    document.fonts?.addEventListener("loadingdone", () => this.#fit());
    // Timers wait while the page is hidden, as when a source is open.
    document.addEventListener("visibilitychange", () => this.#pace());
  }

  // A new session: no cards, and pacing on.
  reset() {
    this.stop();
    this.#cards.clear();
    this.failures = [];
    this.#running = true;
    this.#render();
  }

  // The session is over: the screen stays as it was, and nothing more is
  // paced or reported.
  stop() {
    this.#running = false;
    clearTimeout(this.#timer);
  }

  // A `card` message. A card the page already has is left as it is.
  add(raw) {
    const card = normalise(raw);
    if (!this.#running || !card || this.#cards.has(card.id)) return;
    this.#cards.set(card.id, {card, state: "waiting", seq: this.#seq++});
    this.#pace();
  }

  // A `cards` message after a rejoin: the whole screen again. The server's
  // state stands, except where this page has already moved a card further
  // (shown or filed while the connection was down), since those reports are
  // still on their way. A card the server doesn't list stays as it is here.
  restore({current, waiting, history}) {
    if (!this.#running) return;
    const take = (raw, state) => {
      const card = normalise(raw);
      if (!card) return;
      const c = this.#cards.get(card.id);
      if (!c) this.#cards.set(card.id, {card, state, seq: this.#seq++, shownAt: state === "current" ? Date.now() : undefined});
      else if (RANK[state] > RANK[c.state]) {
        c.state = state;
        if (state === "current") c.shownAt ??= Date.now();
      }
    };
    const local = this.#currentCard();
    for (const raw of list(history)) take(raw, "filed");
    if (current) take(current, "current");
    for (const raw of list(waiting)) take(raw, "waiting");
    // One card on screen: the one this page shows wins.
    const on = [...this.#cards.values()].filter((c) => c.state === "current");
    const keep = on.includes(local) ? local : on[0];
    for (const c of on) if (c !== keep) c.state = "filed";
    this.#pace();
  }

  // ---- pacing ----

  #limits() {
    const c = {...DEFAULTS, ...this.#config()};
    return {minMs: c.min_on_screen_s * 1000, lateMs: c.late_card_s * 1000};
  }

  #currentCard() {
    for (const c of this.#cards.values()) if (c.state === "current") return c;
    return null;
  }

  // In utterance order; cards from the same moment in the order they came.
  #waiting() {
    return [...this.#cards.values()].filter((c) => c.state === "waiting")
      .sort((a, b) => a.card.utt - b.card.utt || a.seq - b.seq);
  }

  #pace() {
    if (!this.#running) return;
    clearTimeout(this.#timer);
    const {minMs, lateMs} = this.#limits();
    const now = Date.now();
    // A waiting card past the cut-off can't reach the screen in time any more.
    for (const c of this.#waiting()) if (now - c.card.utt > lateMs) this.#file(c, true, now);
    let cur = this.#currentCard();
    let waiting = this.#waiting();
    if (cur && waiting.length && now - cur.shownAt >= minMs) {
      this.#file(cur, false, now);
      cur = null;
    }
    while (!cur && waiting.length) {
      const next = waiting.shift();
      if (this.#element(next)) cur = this.#show(next, now);
    }
    // Wake for the next moment something changes by itself.
    waiting = this.#waiting();
    const moments = waiting.map((c) => c.card.utt + lateMs + 1);
    if (cur && waiting.length) moments.push(cur.shownAt + minMs);
    if (moments.length) {
      this.#timer = setTimeout(() => this.#pace(), Math.max(0, Math.min(...moments) - Date.now()) + 5);
    }
    this.#render();
  }

  #tap() {
    const cur = this.#currentCard();
    if (!this.#running || !cur || Date.now() - cur.shownAt < TAP_GUARD_MS) return;
    this.#file(cur, false, Date.now());
    this.#pace();
  }

  #show(c, now) {
    c.state = "current";
    c.shownAt = now;
    this.#report({type: "card_shown", id: c.card.id, at: new Date(now).toISOString()});
    return c;
  }

  #file(c, late, now) {
    c.state = "filed";
    this.#report({type: "card_filed", id: c.card.id, at: new Date(now).toISOString(), late});
  }

  // The card's own screen, built once. A card that fails to render is set
  // aside for the failure buffer and never shown.
  #element(c) {
    if (c.el) return c.el;
    try {
      c.el = currentCard(c.card);
    } catch (e) {
      console.warn("card:", e);
      c.state = "failed";
      this.failures.push({id: c.card.id, at: new Date().toISOString()});
      return null;
    }
    return c.el;
  }

  // ---- drawing ----

  #render() {
    const cur = this.#currentCard();
    if (cur && !this.#element(cur)) return this.#pace();  // failed: the next one goes up
    const id = cur?.card.id ?? null;
    if (id !== this.#shownId) {
      this.#shownId = id;
      this.#current.replaceChildren(...(cur ? [cur.el] : []));
      if (cur) {
        cur.el.classList.toggle("enter", Date.now() - cur.shownAt < 1000);
        this.#fit();
      }
    }
    this.#renderPace(cur);
    this.#renderHistory();
  }

  // "+N waiting" and the bar, which shrinks away over the card's last part
  // of min_on_screen_s. Its row keeps its place when hidden, so the card's
  // type doesn't change size when another card starts waiting.
  #renderPace(cur) {
    const pace = cur?.el.querySelector(".pace");
    if (!pace) return;
    const n = this.#waiting().length;
    const bar = pace.querySelector(".pace-bar");
    for (const a of bar.getAnimations()) a.cancel();
    pace.classList.toggle("on", n > 0);
    if (!n) return;
    pace.querySelector(".waiting").textContent = `+${n} waiting`;
    const {minMs} = this.#limits();
    const left = Math.max(0, cur.shownAt + minMs - Date.now());
    bar.animate([{transform: `scaleX(${left / minMs})`}, {transform: "scaleX(0)"}],
      {duration: Math.max(1, left), easing: "linear", fill: "forwards"});
  }

  #renderHistory() {
    const filed = [...this.#cards.values()].filter((c) => c.state === "filed")
      .sort((a, b) => b.card.utt - a.card.utt || b.seq - a.seq);
    const key = filed.map((c) => c.card.id).join("\n");
    if (key === this.#historyKey) return;
    this.#historyKey = key;
    const rows = [];
    for (const c of filed) {
      try {
        rows.push(historyRow(c.card));
      } catch (e) {
        console.warn("card:", e);
        this.failures.push({id: c.card.id, at: new Date().toISOString()});
      }
    }
    this.#list.replaceChildren(...rows);
    this.#empty.hidden = rows.length > 0;
  }

  // A long fact fits: the card's type scales down (the --fit custom property)
  // until nothing overflows, first with words kept whole. Below MIN_FIT, or
  // at the type's smallest sizes, the fact scrolls within the card instead.
  #fit() {
    const area = this.#current.querySelector(".card-area");
    if (!area || !area.isConnected || !this.#current.clientHeight) return;
    const fact = area.querySelector(".fact");
    const fits = (scale) => {
      area.style.setProperty("--fit", String(scale));
      return fact.scrollHeight <= fact.clientHeight + 1 && fact.scrollWidth <= fact.clientWidth + 1
        && area.scrollHeight <= area.clientHeight + 1 && area.scrollWidth <= area.clientWidth + 1;
    };
    area.classList.add("measuring");
    let best = 1;
    if (!fits(1)) {
      let lo = MIN_FIT, hi = 1;
      for (let i = 0; i < 7; i++) {
        const mid = (lo + hi) / 2;
        if (fits(mid)) lo = mid; else hi = mid;
      }
      best = lo;
    }
    area.style.setProperty("--fit", String(Math.floor(best * 1000) / 1000));
    area.classList.remove("measuring");
    fact.classList.toggle("scrolls", fact.scrollHeight > fact.clientHeight + 1);
    atEnd(fact);
  }
}

// ---- a card's parts ----

// The card as sent, made safe to show: text fields as strings, an unknown
// kind as a claim, and the source URL only if it is http(s).
function normalise(raw) {
  if (!raw || typeof raw !== "object" || raw.id == null || raw.id === "") return null;
  const hedged = raw.band === "hedged";
  const question = raw.kind === "question";
  const utt = Date.parse(raw.utterance_time);
  const url = safeUrl(raw.source?.url);
  return {
    id: String(raw.id),
    kind: question ? "question" : "claim",
    hedged,
    language: /^[a-z]{2,3}(-[a-z0-9]{2,8})*$/i.test(raw.language ?? "") ? raw.language : "",
    label: text(raw.label) || (question ? "Question" : "Claim"),
    tag: hedged ? text(raw.tag) || "Hedged" : "",
    title: text(raw.title),
    fact: text(raw.fact),
    url,
    source: text(raw.source?.title) || (url ? new URL(url).hostname.replace(/^www\./, "") : ""),
    utt: Number.isFinite(utt) ? utt : Date.now(),
  };
}

function text(x) {
  return typeof x === "string" ? x.trim() : "";
}

function safeUrl(x) {
  try {
    const url = new URL(x);
    return url.protocol === "https:" || url.protocol === "http:" ? url.href : null;
  } catch {
    return null;
  }
}

function el(tag, className, content) {
  const e = document.createElement(tag);
  if (className) e.className = className;
  if (content != null) e.textContent = content;
  return e;
}

// The source: a link that opens in a new tab, or plain text without a usable
// URL.
function source(card, className) {
  const p = el("p", className);
  if (!card.url) {
    p.append(el("span", "source-text", card.source));
    return p;
  }
  const a = el("a");
  a.href = card.url;
  a.target = "_blank";
  a.rel = "noopener noreferrer";
  a.append(el("span", "source-text", card.source), el("span", "arrow", "↗"));
  a.querySelector(".arrow").setAttribute("aria-hidden", "true");
  a.setAttribute("aria-label", `Source: ${card.source} (opens in a new tab)`);
  p.append(a);
  return p;
}

function withLanguage(e, card) {
  if (card.language) e.lang = card.language;
  return e;
}

// The current card with its pacing row, filling the region.
function currentCard(card) {
  const area = el("div", "card-area");
  area.dataset.id = card.id;
  area.tabIndex = 0;
  const article = withLanguage(el("article", `card ${card.kind}${card.hedged ? " hedged" : ""}`), card);
  const label = el("p", "label");
  label.append(el("span", "dot"), el("span", "kind", card.label));
  if (card.tag) label.append(el("span", "tag", card.tag));
  const fact = el("p", "fact", card.fact);
  fact.addEventListener("scroll", () => atEnd(fact), {passive: true});
  article.append(label, el("h2", "title", card.title), fact, source(card, "source"));
  const pace = el("div", "pace");
  const track = el("span", "track");
  track.append(el("span", "pace-bar"));
  pace.append(el("span", "waiting"), track);
  area.append(article, pace);
  return area;
}

// A fact that scrolls loses its fade once it is scrolled to the end.
function atEnd(fact) {
  fact.classList.toggle("at-end", fact.scrollTop + fact.clientHeight >= fact.scrollHeight - 2);
}

// An entry (a row) of the card history: ≠ for a claim, ? for a question.
function historyRow(card) {
  const li = withLanguage(el("li", `entry ${card.kind}${card.hedged ? " hedged" : ""}`), card);
  li.dataset.id = card.id;
  const mark = el("span", "entry-mark", card.kind === "question" ? "?" : "≠");
  mark.setAttribute("role", "img");
  mark.setAttribute("aria-label", card.label);
  li.append(mark, el("p", "entry-title", card.title), el("p", "entry-fact", card.fact), source(card, "entry-source"));
  return li;
}

function list(x) {
  return Array.isArray(x) ? x : [];
}
