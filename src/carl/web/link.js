// One WebSocket to the server (spec section 2, One WebSocket): binary frames
// for audio, JSON text frames for everything else, and a heartbeat each way.
// The heartbeat and silence times come in the server's hello, so the config
// file stays the one source of every threshold. The hello also brings the
// month's cost for the Start screen; each hello fires "state" "connected".

const RETRY_MAX_S = 5;  // reconnect after 1, 2, 4, then every 5 s
const TICK_MS = 250;

export class Link extends EventTarget {
  #url; #ws = null; #timer = null; #retry = 1;
  #lastSent = 0; #lastHeard = 0;
  config = null;
  costs = null;
  state = "connecting";

  constructor(url) {
    super();
    this.#url = url;
  }

  connect() {
    const ws = new WebSocket(this.#url);
    ws.binaryType = "arraybuffer";
    this.#ws = ws;
    this.#setState("connecting");
    ws.onmessage = (e) => {
      this.#lastHeard = performance.now();
      if (typeof e.data !== "string") return;
      let message;
      try { message = JSON.parse(e.data); } catch { return; }
      if (message.type === "hello") this.#hello(message);
      else if (message.type !== "heartbeat") {
        this.dispatchEvent(new CustomEvent("message", {detail: message}));
      }
    };
    ws.onclose = () => { if (this.#ws === ws) this.#dropped(); };
  }

  send(message) {
    if (this.#ws?.readyState !== WebSocket.OPEN) return false;
    this.#ws.send(JSON.stringify(message));
    this.#lastSent = performance.now();
    return true;
  }

  sendAudio(chunk) {
    if (this.#ws?.readyState !== WebSocket.OPEN) return false;
    this.#ws.send(chunk);
    this.#lastSent = performance.now();
    return true;
  }

  #hello(message) {
    this.config = message.config;
    this.costs = message.costs ?? null;
    this.#retry = 1;
    this.#lastSent = performance.now();
    clearInterval(this.#timer);
    this.#timer = setInterval(() => this.#tick(), TICK_MS);
    this.#setState("connected");
  }

  #tick() {
    const now = performance.now();
    const {heartbeat_s, silence_s} = this.config.connection;
    if (now - this.#lastHeard >= silence_s * 1000) {
      const ws = this.#ws;
      this.#dropped();
      ws.close(4000, "silence");
    } else if (now - this.#lastSent >= heartbeat_s * 1000) {
      this.send({type: "heartbeat"});
    }
  }

  #dropped() {
    clearInterval(this.#timer);
    this.#timer = null;
    this.#ws = null;
    this.#setState("dropped");
    setTimeout(() => this.connect(), this.#retry * 1000);
    this.#retry = Math.min(this.#retry * 2, RETRY_MAX_S);
  }

  #setState(state) {
    this.state = state;
    this.dispatchEvent(new CustomEvent("state", {detail: state}));
  }
}
