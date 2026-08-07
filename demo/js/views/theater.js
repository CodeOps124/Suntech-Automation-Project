/* theater.js — the Live Automation view.
   Left: the invoice being read (scan line + field highlights).
   Right: the five pipeline stages lighting up in order:
     1 Document understanding (LLM)   — streams what it reads, pens fields
     2 DTAA / TDS analysis (LLM)      — streams reasoning, emits signal chips
     3 Part classification (DETERMINISTIC rules engine) — animated tree
     4 Document checklist             — ticks / flags items
     5 CA handoff                     — automation stops; human certifies
   All driven by bus events emitted from the screenplay in scenario.js. */

"use strict";

import { bus, typewrite } from "../engine.js";
import {
  INVOICE, EXTRACTED_FIELDS, TREE, TREE_RESULT, CHECKLIST,
} from "../data.js";

const esc = s => String(s ?? "").replace(/[&<>"']/g, c =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

export function mountTheater(root) {
  root.innerHTML = `
    <div class="view-head">
      <h1>Live Automation</h1>
      <span class="view-sub">what happens in the seconds after a client uploads an invoice</span>
      <span style="flex:1"></span>
      <span id="hero-status" class="chip st-intake">Intake</span>
    </div>

    <div class="theater">
      <div class="doc-pane">
        <div class="invoice" id="invoice">
          <div class="scanline"></div>
          <div class="inv-stamp">ORIGINAL</div>
          <h2 class="hl" data-hl="inv-seller">${esc(INVOICE.seller)}</h2>
          <div class="inv-meta hl" data-hl="inv-seller">${esc(INVOICE.sellerAddr)}</div>
          <div class="inv-rule"></div>
          <div class="inv-row"><span class="inv-meta">INVOICE</span>
            <span class="mono hl" data-hl="inv-no">${esc(INVOICE.number)}</span></div>
          <div class="inv-row"><span class="inv-meta">DATE</span>
            <span class="hl" data-hl="inv-date">${esc(INVOICE.date)}</span></div>
          <div class="inv-rule"></div>
          <div class="inv-meta">BILL TO</div>
          <div class="hl" data-hl="inv-buyer"><b>${esc(INVOICE.buyer)}</b><br>${esc(INVOICE.buyerAddr)}</div>
          <table class="inv-table hl" data-hl="inv-lines">
            <thead><tr><th>Description</th><th style="text-align:right">Amount</th></tr></thead>
            <tbody>
              ${INVOICE.lines.map(l => `<tr><td>${esc(l.desc)}</td><td style="text-align:right">${esc(l.amount)}</td></tr>`).join("")}
              <tr><td class="inv-total">TOTAL</td>
                  <td class="inv-total hl" data-hl="inv-total" style="text-align:right">${esc(INVOICE.total)}</td></tr>
            </tbody>
          </table>
          <div class="inv-rule"></div>
          <div class="inv-meta">${esc(INVOICE.terms)}</div>
        </div>
      </div>

      <div class="stages">
        ${stageShell(1, "Document understanding", "LLM", `
          <div class="stream" id="read-stream"></div>
          <div class="fields" id="fields"></div>`)}
        ${stageShell(2, "DTAA / TDS analysis", "LLM", `
          <div class="stream" id="dtaa-stream"></div>
          <div class="signals" id="signals"></div>
          <div class="advisory-note">Advisory inputs only — the tax path is decided by the
          deterministic rules engine below, and the CA reviews everything.</div>`)}
        ${stageShell(3, "Part classification", "DETERMINISTIC", `
          <div class="tree" id="tree">
            ${TREE.map(n => `<div class="tnode"><span>${esc(n.q)}</span><span class="tans">${esc(n.a)}</span></div>
              <div class="tarrow">▼</div>`).join("")}
            <div class="tnode result-slot"><span>${esc(TREE_RESULT)}</span><span class="tans">§</span></div>
          </div>
          <div class="rule-stamp">Rule set <code>2024.1</code> · reason codes retained on the case ·
          same input ⇒ same output, always</div>`)}
        ${stageShell(4, "Document checklist", "AUTOMATED", `
          <ul class="check" id="check"></ul>
          <div class="advisory-note" id="chase-note" style="display:none">Gap chase started —
          client portal reminder 1 of 3 sent automatically.</div>`)}
        ${stageShell(5, "CA review & certification", "HUMAN", `
          <div class="handoff">
            <b>Automation stops here.</b> The complete Form 146 pack — extracted data, DTAA
            evidence, reason codes, documents — is queued for the Chartered Accountant.
            The CA reviews, signs with DSC, and generates UDIN. This step is never automated.
            <div class="udin-stamp" id="udin-stamp">UDIN 26123456BKXYZW4821 ✓</div>
          </div>`)}
      </div>
    </div>`;

  wireEvents(root);
}

function stageShell(num, title, tag, body) {
  const tagCls = tag === "LLM" ? "llm" : tag === "DETERMINISTIC" ? "det" : tag === "HUMAN" ? "human" : "";
  return `
    <div class="stage" id="stage-${num}">
      <div class="stage-head">
        <div class="stage-num">${num}</div>
        <div class="stage-title">${esc(title)}</div>
        <div class="stage-tag ${tagCls}">${esc(tag)}</div>
      </div>
      <div class="stage-body">${body}</div>
    </div>`;
}

function wireEvents(root) {
  const $ = sel => root.querySelector(sel);
  const speedOf = () => window.__demoSpeed || 1.6;

  const setStage = (n, cls) => {
    for (let i = 1; i <= 5; i++) {
      const el = $(`#stage-${i}`);
      if (i < n) { el.classList.add("done"); el.classList.remove("active"); }
      else if (i === n) { el.classList.add(cls === "done" ? "done" : "active"); if (cls === "done") el.classList.remove("active"); }
      else { el.classList.remove("active", "done"); }
    }
  };

  bus.on("engine:restart", () => {
    setStage(0);
    $("#read-stream").innerHTML = "";
    $("#dtaa-stream").innerHTML = "";
    $("#fields").innerHTML = "";
    $("#signals").innerHTML = "";
    $("#check").innerHTML = "";
    $("#chase-note").style.display = "none";
    $("#udin-stamp").classList.remove("in");
    $("#invoice").classList.remove("scanning");
    root.querySelectorAll(".hl.lit").forEach(el => el.classList.remove("lit"));
    root.querySelectorAll(".tnode").forEach(el => el.classList.remove("lit", "answered", "result"));
    bus.emit("hero:status", "intake");
  });

  bus.on("hero:status", st => {
    const chip = $("#hero-status");
    chip.className = `chip st-${st}`;
    chip.textContent = ({
      intake: "Intake", extracting: "Extracting", validating: "Validating",
      pending_documents: "Pending docs", ready_for_review: "Awaiting CA",
      certified: "Certified", filed: "Filed",
    })[st] || st;
  });

  bus.on("scan:start", () => { setStage(1); $("#invoice").classList.add("scanning"); });
  bus.on("scan:stop", () => $("#invoice").classList.remove("scanning"));

  bus.on("read:line", async text => {
    const line = document.createElement("span");
    line.className = "sline";
    line.innerHTML = `<span class="pfx">›</span> `;
    $("#read-stream").appendChild(line);
    await typewrite(line, text, { cps: 60, speed: speedOf() });
  });

  bus.on("extract:field", f => {
    // highlight the source region on the invoice, then pen the field down
    root.querySelectorAll(".hl.lit").forEach(el => el.classList.remove("lit"));
    root.querySelectorAll(`.hl[data-hl="${f.hl}"]`).forEach(el => el.classList.add("lit"));
    const el = document.createElement("div");
    el.className = "field" + (f.low ? " low" : "");
    el.innerHTML = `<div class="f-label">${esc(f.label)}</div>
      <div class="f-value">${esc(f.value)}</div>
      <div class="f-conf">confidence ${(f.conf * 100).toFixed(0)}%${f.low ? " · analyst confirm" : ""}</div>`;
    $("#fields").appendChild(el);
    requestAnimationFrame(() => el.classList.add("in"));
  });

  bus.on("dtaa:start", () => {
    root.querySelectorAll(".hl.lit").forEach(el => el.classList.remove("lit"));
    $("#invoice").classList.remove("scanning");
    setStage(2);
  });
  bus.on("dtaa:line", async text => {
    const line = document.createElement("span");
    line.className = "sline";
    line.innerHTML = `<span class="pfx">›</span> `;
    $("#dtaa-stream").appendChild(line);
    await typewrite(line, text, { cps: 65, speed: speedOf() });
  });
  bus.on("dtaa:signal", s => {
    const el = document.createElement("div");
    el.className = "signal";
    el.innerHTML = `${esc(s.k)}: <b>${esc(s.v)}</b>`;
    $("#signals").appendChild(el);
    requestAnimationFrame(() => el.classList.add("in"));
  });

  bus.on("tree:start", () => setStage(3));
  bus.on("tree:step", idx => {
    const nodes = root.querySelectorAll("#tree .tnode:not(.result-slot)");
    nodes.forEach((n, i) => {
      if (i < idx) { n.classList.add("lit", "answered"); }
      else if (i === idx) { n.classList.add("lit"); setTimeout(() => n.classList.add("answered"), 450 / speedOf()); }
    });
  });
  bus.on("tree:result", () => {
    root.querySelector("#tree .result-slot").classList.add("result");
  });

  bus.on("check:start", () => setStage(4));
  bus.on("check:item", item => {
    const li = document.createElement("li");
    li.className = item.ok ? "ok" : "miss";
    li.innerHTML = `<span class="ck">${item.ok ? "✓" : "!"}</span>
      <span>${esc(item.name)}${item.ok ? "" : " — missing, added to gap chase"}</span>`;
    $("#check").appendChild(li);
    requestAnimationFrame(() => li.classList.add("in"));
  });
  bus.on("check:chase", () => { $("#chase-note").style.display = "block"; });
  bus.on("check:resolved", () => {
    root.querySelectorAll("#check li.miss").forEach(li => {
      li.classList.remove("miss"); li.classList.add("ok");
      li.querySelector(".ck").textContent = "✓";
      li.querySelector("span:last-child").textContent =
        li.querySelector("span:last-child").textContent.replace(" — missing, added to gap chase", " — received via client portal");
    });
  });

  bus.on("handoff:start", () => setStage(5));
  bus.on("handoff:certified", () => $("#udin-stamp").classList.add("in"));
  bus.on("handoff:done", () => setStage(6, "done"));
}
