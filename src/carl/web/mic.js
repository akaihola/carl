// The microphone (spec section 4, From the microphone to the server): the
// phone's echo cancellation and noise suppression off and its gain control on,
// resampled by the AudioContext to 16 kHz and cut by mic-worklet.js into
// 100 ms chunks of 16-bit PCM.
//
// It also tells when the open microphone is lost (spec section 10, Can't
// hear): its track ended or was muted, or the permission was revoked; when a
// muted track is back; and when the permission is granted again, so an
// ended track can be replaced.

const RATE = 16000;
const CONSTRAINTS = {audio: {echoCancellation: false, noiseSuppression: false, autoGainControl: true}};

export class Mic {
  #ctx = null; #ready = null; #node = null; #stream = null; #source = null;
  #permission = null;  // the PermissionStatus, where the browser has one
  onchunk = null;  // called with each chunk, an ArrayBuffer
  onlost = null;  // called with "ended", "muted" or "permission"
  onback = null;  // a muted track unmuted
  ongranted = null;  // the permission granted again

  get live() { return this.#stream !== null; }

  get muted() { return !!this.#stream?.getAudioTracks()[0]?.muted; }

  // "granted", "denied", "prompt", or null where the browser doesn't say.
  get permission() { return this.#permission?.state ?? null; }

  // Opens the microphone and returns its track's settings. Call it straight
  // from a tap: the AudioContext is made and resumed before the first await,
  // which browsers that insist on a user gesture need.
  async open() {
    if (!this.#ctx) {
      this.#ctx = new AudioContext({sampleRate: RATE});
      this.#ready = this.#ctx.audioWorklet.addModule(new URL("mic-worklet.js", import.meta.url));
    }
    const ctx = this.#ctx, running = ctx.resume();
    const stream = await navigator.mediaDevices.getUserMedia(CONSTRAINTS);
    try {
      await this.#ready;
      await running;
      if (ctx !== this.#ctx) throw new Error("closed while opening");
      if (!this.#node) {
        // Mono whatever the microphone gives; the node's output stays silent
        // and only keeps it pulled by the audio graph.
        this.#node = new AudioWorkletNode(ctx, "mic", {channelCount: 1, channelCountMode: "explicit"});
        this.#node.port.onmessage = (e) => this.onchunk?.(e.data);
        this.#node.connect(ctx.destination);
      }
      this.#node.port.postMessage("reset");
      this.#release();
      this.#source = ctx.createMediaStreamSource(stream);
      this.#source.connect(this.#node);
      this.#stream = stream;
    } catch (e) {
      for (const track of stream.getTracks()) track.stop();
      throw e;
    }
    const track = stream.getAudioTracks()[0];
    this.#watch(stream, track);
    this.#watchPermission();
    if (track.muted) this.onlost?.("muted");
    return track.getSettings();
  }

  // Only the open stream's track counts; stopping it here fires nothing.
  #watch(stream, track) {
    const current = () => this.#stream === stream;
    track.addEventListener("ended", () => {
      if (current()) this.onlost?.(this.permission === "denied" ? "permission" : "ended");
    });
    track.addEventListener("mute", () => { if (current()) this.onlost?.("muted"); });
    track.addEventListener("unmute", () => { if (current()) this.onback?.(); });
  }

  async #watchPermission() {
    if (this.#permission || !navigator.permissions?.query) return;
    try {
      this.#permission = await navigator.permissions.query({name: "microphone"});
    } catch {
      return;  // not a permission this browser reports
    }
    this.#permission.addEventListener("change", () => {
      if (this.#permission.state === "denied") { if (this.live) this.onlost?.("permission"); }
      else if (this.#permission.state === "granted") this.ongranted?.();
    });
  }

  // Pause: stops the track, so the phone's own microphone indicator goes off,
  // and lets the audio thread idle until the next open().
  close() {
    this.#release();
    this.#ctx?.suspend().catch(() => {});
  }

  // The session is over: the track and the AudioContext both go.
  shutdown() {
    this.#release();
    this.#ctx?.close().catch(() => {});
    this.#ctx = this.#ready = this.#node = null;
  }

  #release() {
    this.#source?.disconnect();
    for (const track of this.#stream?.getTracks() ?? []) track.stop();
    this.#source = this.#stream = null;
  }
}
