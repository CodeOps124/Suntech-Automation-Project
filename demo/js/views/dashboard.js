/* dashboard.js — the firm-wide view, kept alive by the same bus the theater
   runs on: the hero case moves across the board in real time and ambient
   events keep the activity feed humming. */

"use strict";

import { bus } from "../engine.js";
import { BOARD_CASES, BOARD_ORDER, STATUS_LABELS, HERO } from "../data.js";

const esc = s => String(s ?? "").replace(/[&<>"']/g, c =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const state = {
  hero: { ...HERO },
  cases: [],
  filedToday: 1,
  casesToday: 6,
};

export function mountDashboard(root) {
  root.innerHTML = `
    <div class="view-head">
      <h1>Compliance Dashboard</h1>
      <span class="view-sub">firm-wide · live</span>
    </div>
    <div class="tiles">
      <div class="tile accent"><div class="t-label">Cases today</div><div class="t-value" id="tl-today">6</div><div class="t-hint">new remittances opened</div></div>
      <div class="tile"><div class="t-label">In automation</div><div class="t-value" id="tl-auto">–</div><div class="t-hint">OCR · DTAA analysis · doc chase</div></div>
      <div class="tile"><div class="t-label">Awaiting CA review</div><div class="t-value" id="tl-ca">–</div><div class="t-hint">human certification queue</div></div>
      <div class="tile"><div class="t-label">Filed today</div><div class="t-value" id="tl-filed">–</div><div class="t-hint">Form 145 recorded filed</div></div>
    </div>
    <div class="board" id="board"></div>
    <div class="two-col">
      <div class="card">
        <h3 class="card-title">Automation activity</h3>
        <ul class="timeline" id="feed"></ul>
      </div>
      <div class="card">
        <h3 class="card-title">Plan usage — CA Growth</h3>
        <div class="small" style="margin-bottom:8px"><b id="usage-n">6</b> / 100 remittances this month</div>
        <div style="height:10px;background:var(--neutral-wash);border-radius:5px;overflow:hidden">
          <div id="usage-bar" style="height:100%;width:6%;background:var(--info);border-radius:5px;transition:width .6s"></div>
        </div>
        <h3 class="card-title" style="margin-top:18px">Boundary</h3>
        <p class="small muted" style="margin:0">SunComply prepares the case — extraction, DTAA/TDS
        evidence, deterministic Part A–D classification, document chasing, bank-ready pack.
        <b>The CA reviews, certifies with DSC, and generates UDIN — always a human action.</b></p>
      </div>
    </div>`;

  reset();
  bus.on("engine:restart", reset);
  bus.on("hero:status", st => { state.hero.status = st; if (st === "filed") state.filedToday++; paint(); flashHero(); });
  bus.on("hero:part", p => { state.hero.part = p; paint(); });
  bus.on("feed", ev => addFeed(ev));

  function reset() {
    state.hero = { ...HERO };
    state.cases = BOARD_CASES.map(c => ({ ...c }));
    state.filedToday = 1;
    document.getElementById("feed").innerHTML = "";
    paint();
  }

  function paint() {
    const all = [state.hero, ...state.cases];
    const inAuto = all.filter(c => ["intake", "extracting", "validating", "pending_documents"].includes(c.status)).length;
    const awaitCa = all.filter(c => c.status === "ready_for_review").length;
    setTile("tl-auto", inAuto);
    setTile("tl-ca", awaitCa);
    setTile("tl-filed", state.filedToday);
    setTile("tl-today", state.casesToday);

    document.getElementById("board").innerHTML = BOARD_ORDER.map(st => {
      const items = all.filter(c => c.status === st);
      return `<div class="col"><h4>${esc(STATUS_LABELS[st])} <span>${items.length}</span></h4>
        ${items.map(c => `
          <div class="mini-card ${c.id === state.hero.id ? "hero-card" : ""}" data-case="${c.id}">
            <div class="mc-vendor">${esc(c.vendor)}</div>
            <div class="mc-amt">${esc(c.amount)}</div>
            <div class="mc-amt">Part ${esc(c.part || "–")} · ${esc(c.client)}</div>
          </div>`).join("")}
      </div>`;
    }).join("");
  }

  function flashHero() {
    const el = root.querySelector(`.mini-card[data-case="${state.hero.id}"]`);
    if (el) { el.classList.add("flash"); setTimeout(() => el.classList.remove("flash"), 1800); }
  }

  function setTile(id, val) {
    const el = document.getElementById(id);
    if (!el) return;
    if (String(el.textContent) !== String(val)) {
      el.textContent = val;
      el.classList.remove("bump"); void el.offsetWidth; el.classList.add("bump");
    }
  }

  function addFeed(ev) {
    const feed = document.getElementById("feed");
    const li = document.createElement("li");
    li.innerHTML = `<div class="tl-ic ${ev.cls || ""}">${ev.icon || "•"}</div>
      <div><div class="tl-msg">${esc(ev.msg)}</div>
      <div class="tl-time">just now · ${esc(ev.case || "case ee9ab751")}</div></div>`;
    feed.prepend(li);
    while (feed.children.length > 14) feed.lastChild.remove();
  }
}

export function dashboardState() { return state; }
