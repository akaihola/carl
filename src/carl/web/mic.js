// The microphone (spec section 4, From the microphone to the server): the
// phone's echo cancellation and noise suppression off and its gain control on,
// resampled by the AudioContext to 16 kHz and cut by mic-worklet.js into
// 100 ms chunks of 16-bit PCM.

const RATE = 16000;
const CONSTRAINTS = {audio: {echoCancellation: false, noiseSuppression: false, autoGainControl: true}};

export class Mic {
  #ctx = null; #ready = null; #node = null; #stream = null; #source = null;
  onchunk = null;  // called with each chunk, an ArrayBuffer

  get live() { return this.#stream !== null; }

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
    return stream.getAudioTracks()[0].getSettings();
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
