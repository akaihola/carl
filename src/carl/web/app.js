// The page shell. The Start screen and the session screen come with step 2;
// until then the page shows only the connection's state.

import {Link} from "./link.js";

const WORDS = {
  connecting: "Connecting…",
  connected: "Connected",
  dropped: "Connection lost, reconnecting…",
};

const stateEl = document.getElementById("state");
const link = new Link(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/api/ws`);
link.addEventListener("state", (e) => {
  stateEl.dataset.state = e.detail;
  stateEl.textContent = WORDS[e.detail];
});
link.connect();
