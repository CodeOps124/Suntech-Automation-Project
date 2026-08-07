/* cases.js — a presentable case register; the hero row updates live. */

"use strict";

import { bus } from "../engine.js";
import { BOARD_CASES, STATUS_LABELS, HERO } from "../data.js";

const esc = s => String(s ?? "").replace(/[&<>"']/g, c =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const hero = { ...HERO };

export function mountCases(root) {
  bus.on("hero:status", st => { hero.status = st; paint(); });
  bus.on("hero:part", p => { hero.part = p; paint(); });
  bus.on("engine:restart", () => { Object.assign(hero, HERO); paint(); });

  function paint() {
    const rows = [hero, ...BOARD_CASES];
    root.innerHTML = `
      <div class="view-head"><h1>Cases</h1>
        <span class="view-sub">one case = one remittance · full audit trail on every row</span></div>
      <div class="card" style="padding:0">
        <table class="grid">
          <thead><tr><th>Case</th><th>Client</th><th>Vendor</th>
            <th style="text-align:right">Amount</th><th>Part</th><th>Status</th></tr></thead>
          <tbody>
            ${rows.map(c => `<tr>
              <td><code>${esc(c.id)}</code></td>
              <td>${esc(c.client)}</td>
              <td>${esc(c.vendor)}</td>
              <td class="num">${esc(c.amount)}</td>
              <td><span class="part-badge ${c.part === "C" ? "pc" : ""}">${esc(c.part || "–")}</span></td>
              <td><span class="chip st-${esc(c.status)}">${esc(STATUS_LABELS[c.status] || c.status)}</span></td>
            </tr>`).join("")}
          </tbody>
        </table>
      </div>
      <p class="small muted" style="margin-top:12px">Every state change writes an append-only
      <code>case_events</code> row — the audit trail a bank or assessing officer can replay.</p>`;
  }
  paint();
}
