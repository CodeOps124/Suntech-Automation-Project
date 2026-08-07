/* data.js — every piece of simulated content in the demo.
   Nothing here is fetched; this is the screenplay's prop room. */

"use strict";

export const INVOICE = {
  number: "CSI-2026-1187",
  date: "14 Jul 2026",
  seller: "CloudStack Ireland Ltd",
  sellerAddr: "1 Dockland Central, Dublin 1, Ireland · TIN IE6388047V",
  buyer: "Zenith Software Ltd",
  buyerAddr: "Tower B, Cyber City, Gurugram 122002, India · PAN AAACZ9876K",
  lines: [
    { desc: "Enterprise platform licence — annual (5,000 seats)", amount: "€18,90,000" },
    { desc: "Premium support & SLA uplift", amount: "€2,60,000" },
  ],
  total: "€21,50,000",
  terms: "Wire transfer within 30 days · Beneficiary: CloudStack Ireland Ltd, IBAN IE29 AIBK 9311 5212 3456 78",
};

/* Stage 1 — LLM document understanding: fields "penned down" as it reads. */
export const EXTRACTED_FIELDS = [
  { label: "Invoice number",  value: "CSI-2026-1187",          conf: 0.99, hl: "inv-no" },
  { label: "Invoice date",    value: "14 Jul 2026",            conf: 0.98, hl: "inv-date" },
  { label: "Vendor / payee",  value: "CloudStack Ireland Ltd", conf: 0.97, hl: "inv-seller" },
  { label: "Vendor country",  value: "Ireland",                conf: 0.96, hl: "inv-seller" },
  { label: "Vendor TIN",      value: "IE6388047V",             conf: 0.95, hl: "inv-seller" },
  { label: "Remitter",        value: "Zenith Software Ltd",    conf: 0.98, hl: "inv-buyer" },
  { label: "Amount",          value: "EUR 21,50,000",          conf: 0.99, hl: "inv-total" },
  { label: "Nature of payment", value: "Software licence + support", conf: 0.91, hl: "inv-lines" },
  { label: "RBI purpose code", value: "S0802 — software implementation", conf: 0.88, hl: "inv-lines", low: true },
];

export const LLM_READ_LINES = [
  "Reading invoice CSI-2026-1187 … single-page commercial invoice, English.",
  "Identified seller block: CloudStack Ireland Ltd, Dublin — Irish TIN present.",
  "Identified buyer block: Zenith Software Ltd, Gurugram — Indian PAN present.",
  "Two line items: platform licence (annual, 5,000 seats) + premium support.",
  "Total EUR 21,50,000 · payment terms 30 days · IBAN captured for bank pack.",
  "Nature of payment reads as software licence with bundled support — flagging purpose-code suggestion for analyst confirmation.",
];

/* Stage 2 — LLM DTAA/TDS analysis. Advisory inputs, never the decision. */
export const DTAA_LINES = [
  "Vendor is tax-resident in Ireland — India–Ireland DTAA applies if TRC is valid.",
  "Vendor master: TRC on file, valid until 31 Mar 2027 ✓ · Form 10F status: not yet on file.",
  "Payment nature: licence to use standard software + support. Under the DTAA Article 12, royalty definition covers licence fees for the use of software rights.",
  "Domestic law: §9(1)(vi) royalty read with §195 — TDS on gross at 20% (plus surcharge/cess) absent treaty relief.",
  "Treaty rate: Article 12(2) caps royalty withholding at 10% — beneficial rate available if TRC + Form 10F + no-PE declaration are all on file.",
  "No AO lower/nil-TDS order (§195(2)/197) found in the case record.",
  "Prior FY remittances to this vendor: ₹0 — but this single remittance ≈ ₹19.6 Cr at indicative FX, far above the ₹5,00,000 aggregate threshold.",
];

export const DTAA_SIGNALS = [
  { k: "Chargeable to tax", v: "Yes — royalty" },
  { k: "Treaty", v: "India–Ireland DTAA" },
  { k: "Treaty TDS rate", v: "10% (Art. 12)" },
  { k: "Domestic rate", v: "20% u/s 195" },
  { k: "TRC", v: "Valid ✓" },
  { k: "AO certificate", v: "None" },
  { k: "FY aggregate", v: "> ₹5,00,000" },
];

/* Stage 3 — deterministic decision tree (rules 2024.1). */
export const TREE = [
  { q: "Q1 · Chargeable to tax? (DTAA + Rule 37BB(3) exemptions)", a: "YES" },
  { q: "Q2 · Aggregate to this vendor this FY ≤ ₹5,00,000?", a: "NO" },
  { q: "Q3 · AO lower/nil-TDS certificate on file? (§195/197)", a: "NO" },
];
export const TREE_RESULT = "PART C — Form 146 (CA certificate) required before Form 145";

/* Stage 4 — document checklist for a Part C case. */
export const CHECKLIST = [
  { name: "Commercial invoice", ok: true },
  { name: "Licence agreement", ok: false },
  { name: "Tax residency certificate (TRC)", ok: true },
  { name: "Form 10F", ok: false },
  { name: "No-PE declaration", ok: false },
];

/* The hero case + background cases that keep the board alive. */
export const HERO = {
  id: "ee9ab751", vendor: "CloudStack Ireland Ltd", client: "Zenith Software Ltd",
  amount: "€21,50,000", part: null, status: "intake",
};

export const BOARD_CASES = [
  { id: "a1", vendor: "Gulf Machinery Trading LLC", client: "Acme Exports", amount: "AED 3,10,000", part: "A", status: "filed" },
  { id: "a2", vendor: "Meridian Consulting Pte",    client: "Zenith Software", amount: "SGD 9,00,000", part: "C", status: "ready_for_review" },
  { id: "a3", vendor: "Fresh Parts GmbH",           client: "Acme Exports", amount: "€4,20,000", part: "A", status: "certified" },
  { id: "a4", vendor: "Nordic Data AS",             client: "Horizon Textiles", amount: "NOK 6,40,000", part: "B", status: "validating" },
  { id: "a5", vendor: "Kyoto Precision KK",         client: "Acme Exports", amount: "¥1,88,00,000", part: "C", status: "pending_documents" },
];

export const BOARD_ORDER = [
  "intake", "extracting", "validating", "pending_documents",
  "ready_for_review", "certified", "filed",
];
export const STATUS_LABELS = {
  intake: "Intake", extracting: "Extracting", validating: "Validating",
  pending_documents: "Pending docs", ready_for_review: "Awaiting CA",
  certified: "Certified", filed: "Filed",
};

/* Ambient feed events sprinkled between hero beats — the "total system" hum. */
export const AMBIENT_EVENTS = [
  { icon: "✉", cls: "warn", msg: "Reminder 2 of 3 sent — Kyoto Precision KK (licence agreement pending)" },
  { icon: "𝗢", cls: "", msg: "OCR complete — Nordic Data AS invoice (confidence 0.94)" },
  { icon: "✓", cls: "good", msg: "CA certified — Fresh Parts GmbH · UDIN recorded" },
  { icon: "§", cls: "", msg: "Classified Part B — Nordic Data AS (AO certificate on file, rules 2024.1)" },
  { icon: "⇪", cls: "", msg: "Client portal upload — Horizon Textiles added TRC for Nordic Data AS" },
];
