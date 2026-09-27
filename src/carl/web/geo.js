// The phone's location (spec section 12, Updates during a session): while a
// session runs and isn't paused, watchPosition. The first fix goes to the
// server, then a new one only after a move of more than new_fix_distance_m
// from the last one sent, or when the accuracy moves up a level: no
// location, the town only, the full place (the cuts in the hello's config).
// A denial goes once, and Carl doesn't ask again in that session. With the
// Location switch off none of this runs, so the page never asks. The server
// turns fixes into a place name: the page makes no third-party calls. The
// messages are in docs/websocket.md.

const OPTIONS = {enableHighAccuracy: false, maximumAge: 60000};  // a neighbourhood needs no GPS
const EARTH_M = 6371008.8;

export class Geo {
  #send; #config;
  #watch = null;  // the watchPosition id while watching
  #sent = null;  // the last fix sent
  #pending = null;  // a message that couldn't go yet
  #denied = false;

  // `send(message)` returns true if the message went; `config()` gives the
  // hello's location settings.
  constructor(send, config) {
    this.#send = send;
    this.#config = config;
  }

  // A new session: nothing sent yet, and the phone may be asked again.
  reset() {
    this.stop();
    this.#sent = this.#pending = null;
    this.#denied = false;
  }

  start() {
    if (this.#watch !== null || this.#denied || !navigator.geolocation) return;
    this.#watch = navigator.geolocation.watchPosition((p) => this.#fix(p), (e) => this.#error(e), OPTIONS);
  }

  stop() {
    if (this.#watch !== null) navigator.geolocation.clearWatch(this.#watch);
    this.#watch = null;
  }

  // Sends what couldn't go before; call it when the session is back.
  flush() {
    const message = this.#pending;
    if (!message || !this.#send(message)) return;
    this.#pending = null;
    if (message.fix) this.#sent = message.fix;
  }

  #fix(position) {
    const {latitude: lat, longitude: lon, accuracy: accuracy_m} = position.coords;
    const fix = {lat, lon, accuracy_m, time: new Date(position.timestamp).toISOString()};
    const last = this.#sent;
    const moved = !last || distanceM(last, fix) > this.#config().new_fix_distance_m;
    if (!moved && this.#level(fix) <= this.#level(last)) return;
    this.#pending = {type: "location", fix};
    this.flush();
  }

  #error(error) {
    if (error.code !== error.PERMISSION_DENIED) return;  // unavailable or too slow: the watch carries on
    this.stop();
    this.#denied = true;
    this.#pending = {type: "location", denied: true};
    this.flush();
  }

  #level({accuracy_m}) {
    const c = this.#config();
    return accuracy_m > c.no_location_accuracy_m ? 0 : accuracy_m > c.town_only_accuracy_m ? 1 : 2;
  }
}

function distanceM(a, b) {
  const rad = Math.PI / 180, dLat = (b.lat - a.lat) * rad, dLon = (b.lon - a.lon) * rad;
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(a.lat * rad) * Math.cos(b.lat * rad) * Math.sin(dLon / 2) ** 2;
  return 2 * EARTH_M * Math.asin(Math.min(1, Math.sqrt(h)));
}
