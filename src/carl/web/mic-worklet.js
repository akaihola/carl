// Runs on the audio thread (spec section 4, From the microphone to the
// server): turns the 16 kHz mono input into 16-bit little-endian PCM and posts
// it to the page in chunks of 100 ms, each one standing alone.

const CHUNK = 1600;  // samples: 100 ms at 16 kHz, 3200 bytes

class Mic extends AudioWorkletProcessor {
  #chunk = new DataView(new ArrayBuffer(CHUNK * 2));
  #n = 0;

  constructor() {
    super();
    // Any message is "reset": after Pause, no stale samples lead the next chunk.
    this.port.onmessage = () => { this.#n = 0; };
  }

  process([input]) {
    const samples = input[0];
    if (samples) for (const x of samples) {
      const s = Math.max(-1, Math.min(1, x));
      this.#chunk.setInt16(this.#n * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true);
      if (++this.#n === CHUNK) {
        this.port.postMessage(this.#chunk.buffer, [this.#chunk.buffer]);
        this.#chunk = new DataView(new ArrayBuffer(CHUNK * 2));
        this.#n = 0;
      }
    }
    return true;
  }
}

registerProcessor("mic", Mic);
