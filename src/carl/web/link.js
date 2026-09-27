// One WebSocket to the server (spec section 2, One WebSocket): binary frames
// for audio, JSON text frames for everything else, and a heartbeat each way.
// The heartbeat and silence times come in the server's hello, so the config
// file stays the one source of every threshold. The hello also brings the
// month's cost for the Start screen; each hello fires "state" "connected".
//
// The handover (spec section 2, Hosting): the host ends every connection
// after 60 minutes, so at about `handover_s` into a socket's life a second
// one opens. When it has said hello, "handover" fires: the page either
// sends `rejoin` on it with sendNext(), or calls switchover() at once when
// there is no session to carry. After sendNext(), audio is held and send()
// refuses, as while the connection is down, until the page sees the answer
// and calls switchover(): the held audio then goes on the new socket, in
// order, and the old one closes, so no chunk is lost or sent twice and the
// state stays "connected" throughout. A second socket that fails, or
// doesn't take over within `silence_s`, is a dropped connection.

const RETRY_MAX_S = 5;  // reconnect after 1, 2, 4, then every 5 s
const TICK_MS = 250;
const HANDOVER_RETRY_MS = 5000;  // a handover that can't start yet tries again after this
const HELD_MAX = 300;  // audio chunks held during a handover: 30 s, far more than it takes

export class Link extends EventTarget {
  #url; #timer = null; #retry = 1; #handoverTimer = 0;
  #cur = null;  // the socket in use: {ws, lastSent, lastHeard, openedAt, hello}
  #next = null;  // the handover's second socket, until it takes over
  #held = null;  // audio chunks sent while the next socket takes over
  config = null;
  costs = null;
  state = "connecting";
  // Whether a handover may start now; the page defers it while a start or
  // a rejoin is on its way.
  canHandover = () => true;

  constructor(url) {
    super();
    this.#url = url;
  }

  connect() {
    this.#cur = this.#socket();
    this.#setState("connecting");
  }

  // False when it couldn't go: the connection is down, or a handover is
  // under way (the page resends what matters once the session is back).
  send(message) {
    if (this.#held || !isOpen(this.#cur)) return false;
    this.#write(this.#cur, JSON.stringify(message));
    return true;
  }

  // Audio sent during a handover is held and goes on the new socket.
  sendAudio(chunk) {
    if (this.#held) {
      if (this.#held.length < HELD_MAX) this.#held.push(chunk);
      return true;
    }
    if (!isOpen(this.#cur)) return false;
    this.#write(this.#cur, chunk);
    return true;
  }

  // The handover's first message, on the second socket. From now on the
  // page's messages and audio wait for switchover().
  sendNext(message) {
    if (!isOpen(this.#next)) return false;
    this.#write(this.#next, JSON.stringify(message));
    this.#held = [];
    return true;
  }

  // The second socket takes over.
  switchover() {
    const next = this.#next, old = this.#cur;
    if (!next || !next.hello) return;
    this.#next = null;
    this.#cur = next;
    this.config = next.hello.config;
    this.costs = next.hello.costs ?? null;
    for (const item of this.#held ?? []) this.#write(next, item);
    this.#held = null;
    this.#scheduleHandover();
    old.ws.close(1000, "handover");
  }

  // Not now after all (a start or rejoin went out meanwhile): try later.
  abortHandover() {
    const next = this.#next;
    if (!next) return;
    this.#next = null;
    this.#held = null;
    next.ws.close(1000, "handover later");
    clearTimeout(this.#handoverTimer);
    this.#handoverTimer = setTimeout(() => this.#handover(), HANDOVER_RETRY_MS);
  }

  #socket() {
    const ws = new WebSocket(this.#url);
    ws.binaryType = "arraybuffer";
    const now = performance.now();
    const sock = {ws, lastSent: now, lastHeard: now, openedAt: now, hello: null};
    ws.onmessage = (e) => {
      sock.lastHeard = performance.now();
      if (typeof e.data !== "string") return;
      let message;
      try { message = JSON.parse(e.data); } catch { return; }
      if (message.type === "hello") this.#hello(sock, message);
      else if (message.type !== "heartbeat" && (sock === this.#cur || sock === this.#next)) {
        const event = new CustomEvent("message", {detail: message});
        event.handover = sock === this.#next;  // the answer on the second socket
        this.dispatchEvent(event);
      }
    };
    ws.onclose = () => { if (sock === this.#cur || sock === this.#next) this.#dropped(); };
    return sock;
  }

  #write(sock, data) {
    sock.ws.send(data);
    sock.lastSent = performance.now();
  }

  #hello(sock, message) {
    sock.hello = message;
    if (sock === this.#next) {
      this.dispatchEvent(new CustomEvent("handover"));
      return;
    }
    if (sock !== this.#cur) return;
    this.config = message.config;
    this.costs = message.costs ?? null;
    this.#retry = 1;
    sock.openedAt = sock.lastSent = performance.now();
    clearInterval(this.#timer);
    this.#timer = setInterval(() => this.#tick(), TICK_MS);
    this.#scheduleHandover();
    this.#setState("connected");
  }

  #scheduleHandover() {
    clearTimeout(this.#handoverTimer);
    const s = this.config?.connection?.handover_s;
    if (!(s > 0)) return;
    const wait = this.#cur.openedAt + s * 1000 - performance.now();
    this.#handoverTimer = setTimeout(() => this.#handover(), Math.max(0, wait));
  }

  #handover() {
    if (this.state !== "connected" || this.#next) return;
    if (!this.canHandover()) {
      this.#handoverTimer = setTimeout(() => this.#handover(), HANDOVER_RETRY_MS);
      return;
    }
    this.#next = this.#socket();
  }

  #tick() {
    const now = performance.now();
    const {heartbeat_s, silence_s} = this.config.connection;
    const next = this.#next;
    // The old socket must stay heard, and the new one must take over in time.
    if (now - this.#cur.lastHeard >= silence_s * 1000 || (next && now - next.openedAt >= silence_s * 1000)) {
      this.#dropped();
      return;
    }
    for (const sock of [this.#cur, next]) {
      if (sock?.hello && isOpen(sock) && now - sock.lastSent >= heartbeat_s * 1000) this.#write(sock, JSON.stringify({type: "heartbeat"}));
    }
  }

  // The connection is down, the second socket's failure included: both
  // close, and a new one opens after the backoff.
  #dropped() {
    clearInterval(this.#timer);
    clearTimeout(this.#handoverTimer);
    this.#timer = null;
    const socks = [this.#cur, this.#next];
    this.#cur = this.#next = this.#held = null;
    for (const sock of socks) if (sock && sock.ws.readyState < WebSocket.CLOSING) sock.ws.close(4000, "dropped");
    this.#setState("dropped");
    setTimeout(() => this.connect(), this.#retry * 1000);
    this.#retry = Math.min(this.#retry * 2, RETRY_MAX_S);
  }

  #setState(state) {
    this.state = state;
    this.dispatchEvent(new CustomEvent("state", {detail: state}));
  }
}

function isOpen(sock) {
  return sock?.ws.readyState === WebSocket.OPEN;
}
