/* scenario.js — the screenplay.
   One deterministic timeline of beats; each beat waits, then emits bus events.
   The theater, dashboard, and cases views all react to the same events —
   that's the "one system running" illusion, with zero backend. */

"use strict";

import {
  LLM_READ_LINES, EXTRACTED_FIELDS, DTAA_LINES, DTAA_SIGNALS,
  TREE, CHECKLIST, AMBIENT_EVENTS,
} from "./data.js";

const beat = (wait, run) => ({ wait, run });

export function buildScript() {
  const s = [];
  let ambient = 0;
  const dropAmbient = () => {
    const ev = AMBIENT_EVENTS[ambient++ % AMBIENT_EVENTS.length];
    return b => b.emit("feed", { ...ev, case: "other case" });
  };

  /* ── Arrival ─────────────────────────────────────────────────────────── */
  s.push(beat(900, b => {
    b.emit("feed", { icon: "✚", msg: "Client portal upload — Zenith Software Ltd submitted invoice CSI-2026-1187" });
    b.emit("hero:status", "intake");
  }));
  s.push(beat(1400, b => {
    b.emit("hero:status", "extracting");
    b.emit("scan:start");
    b.emit("feed", { icon: "𝗢", msg: "OCR extraction started — CloudStack Ireland Ltd invoice" });
  }));

  /* ── Stage 1: LLM reads the invoice ──────────────────────────────────── */
  for (const line of LLM_READ_LINES) {
    s.push(beat(1500, b => b.emit("read:line", line)));
  }
  for (const f of EXTRACTED_FIELDS) {
    s.push(beat(650, b => b.emit("extract:field", f)));
  }
  s.push(beat(900, b => {
    b.emit("scan:stop");
    b.emit("feed", { icon: "𝗢", cls: "llm", msg: "Document understanding complete — 9 fields extracted, min confidence 0.88" });
  }));
  s.push(beat(400, dropAmbient()));

  /* ── Stage 2: LLM DTAA / TDS analysis ────────────────────────────────── */
  s.push(beat(800, b => {
    b.emit("dtaa:start");
    b.emit("hero:status", "validating");
    b.emit("feed", { icon: "§", cls: "llm", msg: "DTAA/TDS analysis started — India–Ireland treaty, royalty question" });
  }));
  for (const line of DTAA_LINES) {
    s.push(beat(1900, b => b.emit("dtaa:line", line)));
  }
  for (const sig of DTAA_SIGNALS) {
    s.push(beat(420, b => b.emit("dtaa:signal", sig)));
  }
  s.push(beat(700, b =>
    b.emit("feed", { icon: "§", cls: "llm", msg: "DTAA analysis: royalty under Art. 12 — treaty 10% vs domestic 20% — evidence pack noted" })));
  s.push(beat(400, dropAmbient()));

  /* ── Stage 3: deterministic classification ───────────────────────────── */
  s.push(beat(900, b => b.emit("tree:start")));
  TREE.forEach((_, i) => s.push(beat(1300, b => b.emit("tree:step", i))));
  s.push(beat(1200, b => {
    b.emit("tree:result");
    b.emit("hero:part", "C");
    b.emit("feed", { icon: "§", msg: "Classified Part C — rules 2024.1 · Form 146 (CA certificate) required" });
  }));

  /* ── Stage 4: checklist + gap chase ──────────────────────────────────── */
  s.push(beat(1000, b => b.emit("check:start")));
  for (const item of CHECKLIST) {
    s.push(beat(600, b => b.emit("check:item", item)));
  }
  s.push(beat(900, b => {
    b.emit("check:chase");
    b.emit("hero:status", "pending_documents");
    b.emit("feed", { icon: "⚠", cls: "warn", msg: "3 documents missing — reminder 1 of 3 sent to client automatically" });
  }));
  s.push(beat(2600, dropAmbient()));
  s.push(beat(2400, b => {
    b.emit("check:resolved");
    b.emit("feed", { icon: "⇪", msg: "Client uploaded licence agreement, Form 10F, No-PE declaration" });
  }));
  s.push(beat(1300, b => {
    b.emit("hero:status", "validating");
    b.emit("feed", { icon: "→", msg: "Re-validating — checklist complete, classification unchanged (Part C)" });
  }));

  /* ── Stage 5: CA handoff (human) ─────────────────────────────────────── */
  s.push(beat(1400, b => {
    b.emit("handoff:start");
    b.emit("hero:status", "ready_for_review");
    b.emit("feed", { icon: "→", msg: "Form 146 pack queued for CA review — automation stops here" });
  }));
  s.push(beat(3200, b => {
    b.emit("handoff:certified");
    b.emit("hero:status", "certified");
    b.emit("feed", { icon: "✓", cls: "good", msg: "CA Ramesh Iyer certified — DSC signed, UDIN generated" });
  }));
  s.push(beat(2200, b => {
    b.emit("hero:status", "filed");
    b.emit("handoff:done");
    b.emit("feed", { icon: "✓", cls: "good", msg: "Form 145 filed · bank-ready pack generated for the AD" });
  }));

  return s;
}
