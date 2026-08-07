/* main.js — wiring: mount views, build the screenplay, start the engine. */

"use strict";

import { Engine, bus } from "./engine.js";
import { buildScript } from "./scenario.js";
import { mountTheater } from "./views/theater.js";
import { mountDashboard } from "./views/dashboard.js";
import { mountCases } from "./views/cases.js";

/* views */
mountTheater(document.getElementById("view-automation"));
mountDashboard(document.getElementById("view-dashboard"));
mountCases(document.getElementById("view-cases"));

/* nav (hash-based; all views stay mounted so the dashboard keeps moving
   even while you watch the theater) */
function activate(view) {
  document.querySelectorAll(".view").forEach(v => v.classList.add("hidden"));
  document.getElementById(`view-${view}`)?.classList.remove("hidden");
  document.querySelectorAll("#nav a").forEach(a =>
    a.classList.toggle("active", a.dataset.view === view));
}
window.addEventListener("hashchange", () =>
  activate(location.hash.replace("#", "") || "automation"));
activate(location.hash.replace("#", "") || "automation");

/* engine + controls */
const engine = new Engine(buildScript(), { loopDelay: 7000 });
window.__demoSpeed = engine.speed;

const btnPlay = document.getElementById("pb-play");
document.getElementById("pb-restart").addEventListener("click", () => engine.restart());
btnPlay.addEventListener("click", () => engine.toggle());
document.getElementById("pb-speed").addEventListener("change", e => {
  engine.setSpeed(e.target.value);
  window.__demoSpeed = engine.speed;
});
bus.on("engine:state", ({ playing }) => { btnPlay.textContent = playing ? "⏸" : "▶"; });

/* theme */
document.getElementById("theme-toggle").addEventListener("click", () => {
  const root = document.documentElement;
  root.dataset.theme = root.dataset.theme === "dark" ? "light" : "dark";
});
const themeParam = new URLSearchParams(location.search).get("theme");
if (themeParam) document.documentElement.dataset.theme = themeParam;

/* action — one restart to zero everything, then run */
engine.restart();
