/* SunComply 145 web application.
   Plain JavaScript against the platform API. Live views refresh every four
   seconds. Certification is a human action behind an explicit confirmation
   dialog and the server enforces the reviewer role. */

"use strict";

const API = "/api/v1";
const POLL_MS = 4000;

const state = {
  session: null,          // { token, user, firm } from /auth/login
  users: [],
  clients: [],
  vendors: [],
  statusFilter: null,
  invoiceSearch: "",
  poller: null,
  currentCaseId: null,
  demo: null,             // live demo runner state
};

const STATUS_LABELS = {
  intake: "Intake",
  extracting: "Extracting",
  validating: "Validating",
  pending_documents: "Pending docs",
  ready_for_review: "Awaiting CA",
  certified: "Certified",
  filed: "Filed",
  exception: "Exception",
};
const BOARD_ORDER = [
  "intake", "extracting", "validating", "pending_documents",
  "ready_for_review", "certified", "filed", "exception",
];
const DOC_TYPES = [
  ["invoice", "Invoice"], ["agreement", "Agreement"], ["trc", "Tax residency certificate"],
  ["form_10f", "Form 10F"], ["no_pe_declaration", "No PE declaration"],
  ["ao_certificate", "AO certificate"], ["other", "Other"],
];
const EVENT_ICONS = {
  case_created: ["+", ""], status_changed: ["→", ""], ocr_completed: ["O", ""],
  classified: ["§", ""], document_uploaded: ["⇪", ""], document_gap_detected: ["!", "warn"],
  reminder_sent: ["✉", "warn"], certified: ["✓", "good"], filed: ["✓", "good"],
  exception_raised: ["!", "bad"], warning_raised: ["!", "warn"],
};
const VIEW_TITLES = {
  dashboard: "Dashboard", invoices: "E-Invoices", cases: "Cases", new: "New Remittance",
  directory: "Clients and Vendors", demo: "Live Demo", settings: "Settings",
};

/* ---------- helpers ---------- */

async function api(path, opts = {}) {
  opts.headers = Object.assign(
    {
      "X-Firm-ID": state.session.firm.id,
      "Authorization": "Bearer " + state.session.token,
    },
    opts.headers || {}
  );
  const res = await fetch(API + path, opts);
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail || detail; } catch (_) { /* keep statusText */ }
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  const ct = res.headers.get("content-type") || "";
  return ct.includes("application/json") ? res.json() : res;
}

function toast(msg, kind = "") {
  const el = document.createElement("div");
  el.className = `toast ${kind}`;
  el.textContent = msg;
  document.getElementById("toast-rack").appendChild(el);
  setTimeout(() => el.remove(), 4200);
}

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, c =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function fmtAmount(amount, currency) {
  if (amount == null) return "";
  const n = Number(amount);
  try {
    return new Intl.NumberFormat("en-IN", { style: "currency", currency: currency || "INR", maximumFractionDigits: 0 }).format(n);
  } catch (_) { return `${currency || ""} ${n.toLocaleString("en-IN")}`; }
}
function fmtTime(iso) {
  const d = new Date(iso);
  return d.toLocaleString("en-IN", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
}
function shortId(id) { return id ? id.slice(0, 8) : ""; }
function chip(status) {
  return `<span class="chip st-${esc(status)}">${esc(STATUS_LABELS[status] || status)}</span>`;
}
function partBadge(part) {
  if (!part) return `<span class="part-badge" title="Not classified yet">–</span>`;
  const cls = part === "C" ? "part-badge pc" : "part-badge";
  return `<span class="${cls}" title="Form 145 Part ${esc(part)}">${esc(part)}</span>`;
}
function vendorName(id) { return (state.vendors.find(v => v.id === id) || {}).name || ""; }
function clientName(id) { return (state.clients.find(c => c.id === id) || {}).name || ""; }
function canCertifyRole() {
  return ["ca_reviewer", "admin"].includes(state.session.user.role);
}

function stopPolling() { if (state.poller) { clearInterval(state.poller); state.poller = null; } }
function startPolling(fn) { stopPolling(); state.poller = setInterval(fn, POLL_MS); }

async function loadDirectory() {
  [state.clients, state.vendors, state.users] = await Promise.all([
    api("/clients"), api("/vendors"), api("/users"),
  ]);
}

const viewEl = () => document.getElementById("view");

/* ---------- session ---------- */

function loadSession() {
  try {
    const raw = localStorage.getItem("session");
    if (raw) state.session = JSON.parse(raw);
  } catch (_) { state.session = null; }
}

function showLogin() {
  stopPolling();
  document.getElementById("app-shell").classList.add("hidden");
  document.getElementById("login-screen").classList.remove("hidden");
}

function showApp() {
  document.getElementById("login-screen").classList.add("hidden");
  document.getElementById("app-shell").classList.remove("hidden");
  const u = state.session.user;
  const initials = u.name.split(/\s+/).map(w => w[0]).join("").slice(0, 2).toUpperCase();
  document.getElementById("user-avatar").textContent = initials;
  document.getElementById("ud-name").textContent = u.name;
  document.getElementById("ud-mail").textContent = u.email;
  document.getElementById("ud-role").textContent = u.role.replace("_", " ");
  document.getElementById("topbar-firm").textContent = state.session.firm.name;
}

function signOut() {
  localStorage.removeItem("session");
  state.session = null;
  location.hash = "";
  showLogin();
}

/* ---------- views ---------- */

async function renderDashboard() {
  stopPolling();
  const paint = async () => {
    const [stats, activity, usage, cases] = await Promise.all([
      api("/dashboard/stats"), api("/dashboard/activity?limit=14"),
      api("/dashboard/usage"), api("/cases"),
    ]);
    const used = usage.used_this_month, inc = usage.included_remittances;
    const pct = Math.min(100, Math.round((used / inc) * 100));
    const meterCls = used > inc ? "over" : (pct >= 80 ? "warn" : "");
    const planLabel = usage.plan.replace(/^ca_/, "CA ").replace(/_/g, " ");

    const cols = BOARD_ORDER.map(st => {
      const items = cases.filter(c => c.status === st);
      return `<div class="col"><h4>${esc(STATUS_LABELS[st])} <span class="count">${items.length}</span></h4>
        ${items.slice(0, 6).map(c => `
          <div class="mini-card" onclick="location.hash='#/cases/${c.id}'">
            <div class="mc-vendor">${esc(vendorName(c.vendor_id) || "No vendor")}</div>
            <div class="mc-amt">${fmtAmount(c.amount, c.currency)}</div>
            <div class="mc-part">Part ${esc(c.part_classification || "–")} · ${esc(clientName(c.client_id))}</div>
          </div>`).join("")}
        ${items.length > 6 ? `<div class="empty">+${items.length - 6} more</div>` : ""}
      </div>`;
    }).join("");

    viewEl().innerHTML = `
      <div class="view-head">
        <h1>Compliance Dashboard</h1>
        <span class="view-sub">Live view, refreshes every ${POLL_MS / 1000} seconds</span>
      </div>
      <div class="tiles">
        <div class="tile accent"><div class="t-label">Cases today</div><div class="t-value">${stats.cases_today}</div><div class="t-hint">new remittances opened</div></div>
        <div class="tile"><div class="t-label">In automation</div><div class="t-value">${stats.in_automation}</div><div class="t-hint">extraction, validation, document chase</div></div>
        <div class="tile"><div class="t-label">Awaiting CA review</div><div class="t-value">${stats.awaiting_ca_review}</div><div class="t-hint">human certification queue</div></div>
        <div class="tile"><div class="t-label">Filed today</div><div class="t-value">${stats.filed_today}</div><div class="t-hint">Form 145 recorded filed</div></div>
      </div>

      <div class="card section-gap">
        <h3 class="card-title">Plan usage, ${esc(planLabel)}</h3>
        <div class="meter-row">
          <span class="small"><b>${used}</b> of ${inc} remittances this month</span>
          <div class="meter"><i class="${meterCls}" style="width:${pct}%"></i></div>
          <span class="small muted">overage ${usage.overage_count} at ₹${esc(usage.overage_rate_inr)} each, total ₹${esc(usage.overage_charge_inr)}</span>
        </div>
      </div>

      <div class="section-gap">
        <h3 class="card-title">Case pipeline</h3>
        <div class="board">${cols}</div>
      </div>

      <div class="two-col section-gap">
        <div class="card">
          <h3 class="card-title">Automation activity</h3>
          <ul class="timeline">${activity.map(evRow).join("") || `<div class="empty">No activity yet</div>`}</ul>
        </div>
        <div class="card">
          <h3 class="card-title">How responsibility is divided</h3>
          <p class="small muted" style="margin:0">The platform prepares each case: it extracts the
          invoice data, classifies the tax path under the current rule set, chases missing documents
          and assembles the review pack. <b>The CA reviews, certifies with DSC and generates the
          UDIN. That step is always a human action.</b> Certification fees and bank charges are never
          billed through the platform.</p>
        </div>
      </div>`;
  };
  await paint();
  startPolling(() => paint().catch(() => {}));
}

function evRow(e) {
  const [ic, cls] = EVENT_ICONS[e.event_type] || ["•", ""];
  return `<li><div class="tl-ic ${cls}">${ic}</div>
    <div class="tl-body"><div class="tl-msg">${esc(e.message || e.event_type)}</div>
    <div class="tl-time">${fmtTime(e.created_at)} · case ${shortId(e.case_id)}</div></div></li>`;
}

/* ---------- E-Invoices ---------- */

async function renderInvoices() {
  stopPolling();
  const paint = async () => {
    const [docs, cases] = await Promise.all([api("/documents"), api("/cases")]);
    const caseById = Object.fromEntries(cases.map(c => [c.id, c]));
    const q = state.invoiceSearch.trim().toLowerCase();
    const rows = docs.filter(d => {
      if (!q) return true;
      const c = caseById[d.case_id] || {};
      return (d.original_filename || "").toLowerCase().includes(q)
        || vendorName(c.vendor_id).toLowerCase().includes(q)
        || clientName(c.client_id).toLowerCase().includes(q);
    });
    const typeLabel = (t) => (DOC_TYPES.find(([v]) => v === t) || [t, t])[1];

    viewEl().innerHTML = `
      <div class="view-head">
        <h1>E-Invoices</h1>
        <span class="view-sub">every document received across your cases</span>
        <span class="spacer"></span>
        <button class="btn btn-gold" onclick="location.hash='#/new'">＋ New remittance</button>
      </div>
      <div class="filter-row">
        <input id="inv-search" class="fld search-box" placeholder="Search file, client or vendor"
          value="${esc(state.invoiceSearch)}" oninput="setInvoiceSearch(this.value)">
        <span class="small muted">${rows.length} of ${docs.length} documents</span>
      </div>
      <div class="card" style="padding:0">
        <table class="grid">
          <thead><tr><th>Document</th><th>Type</th><th>Client</th><th>Vendor</th>
            <th style="text-align:right">Amount</th><th>Status</th>
            <th style="text-align:right">Confidence</th><th></th></tr></thead>
          <tbody>
            ${rows.map(d => {
              const c = caseById[d.case_id] || {};
              return `<tr class="rowlink" onclick="location.hash='#/cases/${d.case_id}'">
                <td>${esc(d.original_filename || "file")}</td>
                <td class="small muted">${esc(typeLabel(d.doc_type))}</td>
                <td>${esc(clientName(c.client_id))}</td>
                <td>${esc(vendorName(c.vendor_id))}</td>
                <td class="num">${fmtAmount(c.amount, c.currency)}</td>
                <td>${chip(c.status || "intake")}</td>
                <td class="num">${d.confidence_score != null ? (Number(d.confidence_score) * 100).toFixed(0) + "%" : "queued"}</td>
                <td><button class="btn" style="padding:4px 10px;font-size:12px"
                  onclick="event.stopPropagation(); downloadDocument('${d.id}', '${esc(d.original_filename || "document")}')">Download</button></td>
              </tr>`;
            }).join("") || `<tr><td colspan="8"><div class="empty">No documents yet. Open a remittance and upload the invoice.</div></td></tr>`}
          </tbody>
        </table>
      </div>`;
    const search = document.getElementById("inv-search");
    if (q) { search.focus(); search.setSelectionRange(search.value.length, search.value.length); }
  };
  await paint();
  startPolling(() => paint().catch(() => {}));
}

window.setInvoiceSearch = (v) => { state.invoiceSearch = v; renderInvoices(); };

window.downloadDocument = async (docId, filename) => {
  try {
    const res = await api(`/documents/${docId}/file`);
    const blob = await res.blob();
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = filename;
    a.click();
    URL.revokeObjectURL(a.href);
  } catch (e) { toast(e.message, "err"); }
};

/* ---------- Cases ---------- */

async function renderCases() {
  stopPolling();
  const paint = async () => {
    const cases = await api("/cases" + (state.statusFilter ? `?status_filter=${state.statusFilter}` : ""));
    const filters = ["", ...BOARD_ORDER].map(st => `
      <button class="filter-chip ${state.statusFilter === (st || null) ? "on" : ""}"
        onclick="setFilter('${st}')">${st ? esc(STATUS_LABELS[st]) : "All"}</button>`).join("");
    viewEl().innerHTML = `
      <div class="view-head"><h1>Cases</h1><span class="view-sub">one case per remittance</span>
        <span class="spacer"></span>
        <button class="btn btn-gold" onclick="location.hash='#/new'">＋ New remittance</button></div>
      <div class="filter-row">${filters}</div>
      <div class="card" style="padding:0">
        <table class="grid">
          <thead><tr><th>Case</th><th>Client</th><th>Vendor</th><th style="text-align:right">Amount</th><th>Part</th><th>Status</th><th>Opened</th></tr></thead>
          <tbody>
            ${cases.map(c => `
              <tr class="rowlink" onclick="location.hash='#/cases/${c.id}'">
                <td><code>${shortId(c.id)}</code></td>
                <td>${esc(clientName(c.client_id))}</td>
                <td>${esc(vendorName(c.vendor_id))}</td>
                <td class="num">${fmtAmount(c.amount, c.currency)}</td>
                <td>${partBadge(c.part_classification)}</td>
                <td>${chip(c.status)}</td>
                <td class="small muted">${fmtTime(c.created_at)}</td>
              </tr>`).join("") || `<tr><td colspan="7"><div class="empty">No cases</div></td></tr>`}
          </tbody>
        </table>
      </div>`;
  };
  await paint();
  startPolling(() => paint().catch(() => {}));
}

window.setFilter = (st) => { state.statusFilter = st || null; renderCases(); };

async function renderCaseDetail(caseId) {
  stopPolling();
  state.currentCaseId = caseId;
  const paint = async () => {
    const [c, events] = await Promise.all([
      api(`/cases/${caseId}`), api(`/cases/${caseId}/events`),
    ]);
    const cr = c.classification_reasons || {};
    const canCertify = c.status === "ready_for_review" && canCertifyRole();
    const canFile = c.status === "certified" && canCertifyRole();
    const canPack = c.status === "certified" || c.status === "filed";

    viewEl().innerHTML = `
      <div class="view-head">
        <h1>Case <code>${shortId(c.id)}</code></h1>
        ${chip(c.status)} ${partBadge(c.part_classification)}
        <span class="spacer"></span>
        <button class="btn" onclick="location.hash='#/cases'">Back to cases</button>
      </div>

      <div class="detail-grid">
        <div>
          <div class="card">
            <h3 class="card-title">Remittance</h3>
            <dl class="kv">
              <dt>Client</dt><dd>${esc(clientName(c.client_id))}</dd>
              <dt>Vendor</dt><dd>${esc(vendorName(c.vendor_id) || "Not set")}</dd>
              <dt>Amount</dt><dd><b>${fmtAmount(c.amount, c.currency) || "Not set"}</b></dd>
              <dt>RBI purpose code</dt><dd>${esc(c.purpose_code || "Not set")}</dd>
              <dt>Remittance date</dt><dd>${esc(c.remittance_date || "Not set")}</dd>
              <dt>Opened</dt><dd>${fmtTime(c.created_at)}</dd>
              ${c.udin ? `<dt>UDIN</dt><dd><code>${esc(c.udin)}</code></dd>` : ""}
              ${c.dsc_reference ? `<dt>DSC reference</dt><dd><code>${esc(c.dsc_reference)}</code></dd>` : ""}
              ${c.certified_at ? `<dt>Certified at</dt><dd>${fmtTime(c.certified_at)}</dd>` : ""}
            </dl>
          </div>

          <div class="card section-gap">
            <h3 class="card-title">Classification, deterministic rules engine</h3>
            ${c.part_classification ? `
              <div class="small" style="margin-bottom:8px">Part <b>${esc(c.part_classification)}</b>
                · rule set <code>${esc(cr.rule_version || "?")}</code>
                ${cr.requires_ca_certificate ? " · <b>Form 146 CA certificate required</b>" : ""}</div>
              ${(cr.reasons || []).map(r => `<div class="reason-item">${esc(r)}</div>`).join("")}
              ${(cr.warnings || []).map(w => `<div class="warning-item">${esc(w)}</div>`).join("")}`
            : `<div class="empty">Not classified yet. Classification runs automatically after extraction.</div>`}
          </div>

          <div class="card section-gap">
            <h3 class="card-title">Documents</h3>
            <div id="doc-list"><div class="empty">Loading</div></div>
            <div style="display:flex;gap:8px;margin-top:12px;flex-wrap:wrap">
              <input type="file" id="doc-file" class="fld" style="flex:2;min-width:180px">
              <select id="doc-type" class="fld" style="flex:1;min-width:150px">
                ${DOC_TYPES.map(([v, l]) => `<option value="${v}">${l}</option>`).join("")}
              </select>
              <button class="btn btn-primary" onclick="uploadDoc('${c.id}')">Upload</button>
            </div>
            <div class="small muted" style="margin-top:6px">Upload starts the automation pipeline. Watch the timeline update live.</div>
          </div>
        </div>

        <div>
          <div class="card">
            <h3 class="card-title">Actions</h3>
            <div style="display:flex;flex-direction:column;gap:8px">
              <button class="btn btn-gold" ${canCertify ? "" : "disabled"}
                onclick="openCertify()">CA certify with DSC and UDIN</button>
              <button class="btn" ${canFile ? "" : "disabled"} onclick="markFiled('${c.id}')">Record Form 145 filed</button>
              <button class="btn" ${canPack ? "" : "disabled"} onclick="downloadPack('${c.id}')">Download bank pack PDF</button>
            </div>
            <div class="small muted" style="margin-top:10px">
              ${canCertifyRole()
                ? "Certify is enabled only when the case is Awaiting CA. Automation stops at the review queue."
                : "Your role cannot certify. A CA reviewer signs this step."}</div>
          </div>

          <div class="card section-gap">
            <h3 class="card-title">Audit timeline</h3>
            <ul class="timeline">${events.slice().reverse().map(evRow).join("") || `<div class="empty">No events</div>`}</ul>
          </div>
        </div>
      </div>`;

    paintDocs(c.id).catch(() => {});
  };
  await paint();
  startPolling(() => paint().catch(() => {}));
}

async function paintDocs(caseId) {
  const docs = await api(`/cases/${caseId}/documents`);
  const el = document.getElementById("doc-list");
  if (!el) return;
  const typeLabel = (t) => (DOC_TYPES.find(([v]) => v === t) || [t, t])[1];
  el.innerHTML = docs.length
    ? `<table class="grid"><thead><tr><th>Document</th><th>Type</th><th style="text-align:right">OCR confidence</th></tr></thead><tbody>
        ${docs.map(d => `<tr>
          <td>${esc(d.original_filename || "file")}</td>
          <td class="small muted">${esc(typeLabel(d.doc_type))}</td>
          <td class="num">${d.confidence_score != null ? (Number(d.confidence_score) * 100).toFixed(0) + "%" : "queued"}</td>
        </tr>`).join("")}
      </tbody></table>`
    : `<div class="empty">No documents yet. Upload the invoice to begin.</div>`;
}

window.uploadDoc = async (caseId) => {
  const fileInput = document.getElementById("doc-file");
  const docType = document.getElementById("doc-type").value;
  if (!fileInput.files.length) { toast("Choose a file first", "err"); return; }
  const fd = new FormData();
  fd.append("file", fileInput.files[0]);
  fd.append("doc_type", docType);
  try {
    await api(`/cases/${caseId}/documents`, { method: "POST", body: fd });
    toast("Document uploaded, automation pipeline queued", "ok");
  } catch (e) { toast(`Upload failed: ${e.message}`, "err"); }
};

window.openCertify = () => {
  const u = state.session.user;
  document.getElementById("certify-actor").textContent = `${u.name} (${u.role.replace("_", " ")})`;
  document.getElementById("certify-error").classList.add("hidden");
  document.getElementById("dsc-input").value = "";
  document.getElementById("udin-input").value = "";
  document.getElementById("certify-overlay").classList.remove("hidden");
};

window.markFiled = async (caseId) => {
  try {
    await api(`/cases/${caseId}/file?actor_user_id=${state.session.user.id}`, { method: "POST" });
    toast("Form 145 filing recorded", "ok");
  } catch (e) { toast(e.message, "err"); }
};

window.downloadPack = async (caseId) => {
  try {
    const res = await api(`/cases/${caseId}/bank-pack`);
    const blob = await res.blob();
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `bank-pack-${shortId(caseId)}.pdf`;
    a.click();
    URL.revokeObjectURL(a.href);
  } catch (e) { toast(e.message, "err"); }
};

/* ---------- New Remittance ---------- */

async function renderNewCase() {
  stopPolling();
  await loadDirectory();
  const clientOpts = state.clients.map(c => `<option value="${c.id}">${esc(c.name)}</option>`).join("");
  viewEl().innerHTML = `
    <div class="view-head"><h1>New Remittance</h1>
      <span class="view-sub">opens one Form 145 case, then upload the invoice</span></div>
    <div class="card" style="max-width:640px">
      <div class="form-grid">
        <div><label class="fld-label">Client, the remitter</label>
          <select id="nc-client" class="fld">${clientOpts}</select></div>
        <div><label class="fld-label">Vendor, the foreign payee</label>
          <select id="nc-vendor" class="fld"></select></div>
        <div><label class="fld-label">Amount</label>
          <input id="nc-amount" class="fld" type="number" min="0" step="0.01" placeholder="250000"></div>
        <div><label class="fld-label">Currency</label>
          <input id="nc-currency" class="fld" list="ccy" maxlength="3" placeholder="AED" style="text-transform:uppercase">
          <datalist id="ccy"><option>AED</option><option>USD</option><option>EUR</option><option>GBP</option><option>SGD</option><option>INR</option></datalist></div>
        <div><label class="fld-label">RBI purpose code</label>
          <input id="nc-purpose" class="fld" placeholder="S0101"></div>
        <div><label class="fld-label">Remittance date</label>
          <input id="nc-date" class="fld" type="date"></div>
        <div class="full"><label class="fld-label">Invoice file, optional, starts automation at once</label>
          <input id="nc-file" class="fld" type="file"></div>
        <div class="full"><button class="btn btn-primary" style="width:100%" onclick="createCase()">Open case</button></div>
      </div>
    </div>`;
  const syncVendors = () => {
    const cid = document.getElementById("nc-client").value;
    document.getElementById("nc-vendor").innerHTML =
      state.vendors.filter(v => v.client_id === cid)
        .map(v => `<option value="${v.id}">${esc(v.name)}${v.country ? ", " + esc(v.country) : ""}</option>`).join("")
      || `<option value="">No vendors for this client</option>`;
  };
  document.getElementById("nc-client").addEventListener("change", syncVendors);
  syncVendors();
}

window.createCase = async () => {
  const payload = {
    client_id: document.getElementById("nc-client").value,
    vendor_id: document.getElementById("nc-vendor").value || null,
    amount: document.getElementById("nc-amount").value || null,
    currency: (document.getElementById("nc-currency").value || "").toUpperCase() || null,
    purpose_code: document.getElementById("nc-purpose").value || null,
    remittance_date: document.getElementById("nc-date").value || null,
  };
  const fileInput = document.getElementById("nc-file");
  try {
    const c = await api("/cases", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (fileInput.files.length) {
      const fd = new FormData();
      fd.append("file", fileInput.files[0]);
      fd.append("doc_type", "invoice");
      await api(`/cases/${c.id}/documents`, { method: "POST", body: fd });
      toast("Case opened and invoice uploaded, automation running", "ok");
    } else {
      toast("Case opened. Upload the invoice to start automation.", "ok");
    }
    location.hash = `#/cases/${c.id}`;
  } catch (e) { toast(e.message, "err"); }
};

/* ---------- Directory ---------- */

async function renderDirectory() {
  stopPolling();
  await loadDirectory();
  viewEl().innerHTML = `
    <div class="view-head"><h1>Clients and Vendors</h1></div>
    <div class="two-col">
      <div class="card">
        <h3 class="card-title">Clients, the remitters</h3>
        <table class="grid"><thead><tr><th>Name</th><th>PAN</th></tr></thead><tbody>
          ${state.clients.map(c => `<tr><td>${esc(c.name)}</td><td><code>${esc(c.pan || "")}</code></td></tr>`).join("")}
        </tbody></table>
        <div style="display:flex;gap:8px;margin-top:12px">
          <input id="cl-name" class="fld" placeholder="Client name">
          <input id="cl-pan" class="fld" placeholder="PAN" style="max-width:130px">
          <button class="btn btn-primary" onclick="addClient()">Add</button>
        </div>
      </div>
      <div class="card">
        <h3 class="card-title">Vendors, the foreign payees</h3>
        <table class="grid"><thead><tr><th>Name</th><th>Country</th><th>Client</th></tr></thead><tbody>
          ${state.vendors.map(v => `<tr><td>${esc(v.name)}</td><td>${esc(v.country || "")}</td><td class="small muted">${esc(clientName(v.client_id))}</td></tr>`).join("")}
        </tbody></table>
        <div style="display:flex;gap:8px;margin-top:12px;flex-wrap:wrap">
          <select id="vn-client" class="fld" style="min-width:140px;flex:1">
            ${state.clients.map(c => `<option value="${c.id}">${esc(c.name)}</option>`).join("")}
          </select>
          <input id="vn-name" class="fld" placeholder="Vendor name" style="flex:1;min-width:140px">
          <input id="vn-country" class="fld" placeholder="Country" style="max-width:120px">
          <button class="btn btn-primary" onclick="addVendor()">Add</button>
        </div>
      </div>
    </div>`;
}

window.addClient = async () => {
  try {
    await api("/clients", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: document.getElementById("cl-name").value, pan: document.getElementById("cl-pan").value || null }),
    });
    toast("Client added", "ok"); renderDirectory();
  } catch (e) { toast(e.message, "err"); }
};
window.addVendor = async () => {
  try {
    await api("/vendors", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        client_id: document.getElementById("vn-client").value,
        name: document.getElementById("vn-name").value,
        country: document.getElementById("vn-country").value || null,
      }),
    });
    toast("Vendor added", "ok"); renderDirectory();
  } catch (e) { toast(e.message, "err"); }
};

/* ---------- Live Demo ---------- */

const DEMO_STEPS = [
  "Prepare demo client and vendor",
  "Open a remittance case",
  "Upload a sample invoice",
  "Automation extracts and classifies",
  "Case reaches the CA review queue",
];

async function renderDemo() {
  stopPolling();
  const d = state.demo || { running: false, current: -1, info: {}, caseId: null, done: false };
  state.demo = d;
  viewEl().innerHTML = `
    <div class="view-head"><h1>Live Demo</h1>
      <span class="view-sub">runs a real case through the automation, nothing is simulated</span></div>
    <div class="two-col">
      <div class="card">
        <h3 class="card-title">End to end run</h3>
        <ul class="demo-steps">
          ${DEMO_STEPS.map((name, i) => {
            let dotCls = "", dotTxt = i + 1;
            if (d.current === i && d.running) { dotCls = "run"; dotTxt = "…"; }
            else if (d.current > i || d.done) { dotCls = "done"; dotTxt = "✓"; }
            if (d.failed === i) { dotCls = "fail"; dotTxt = "!"; }
            return `<li><div class="step-dot ${dotCls}">${dotTxt}</div>
              <div><div class="step-name">${esc(name)}</div>
              <div class="step-info">${esc(d.info[i] || "")}</div></div></li>`;
          }).join("")}
        </ul>
        <div style="display:flex;gap:8px;margin-top:16px">
          <button class="btn btn-primary grow" id="demo-run" ${d.running ? "disabled" : ""}
            onclick="runDemo()">${d.done ? "Run again" : "Run the demo"}</button>
          ${d.caseId ? `<button class="btn" onclick="location.hash='#/cases/${d.caseId}'">Open the case</button>` : ""}
        </div>
      </div>
      <div class="card">
        <h3 class="card-title">What this shows</h3>
        <p class="small muted" style="margin:0 0 10px">The run creates a real case in your workspace
        and pushes a generated invoice through the same pipeline production uses: object storage,
        extraction with a confidence score, the versioned Part A to D rules engine, the document
        checklist and the append only audit trail.</p>
        <p class="small muted" style="margin:0">It stops at the review queue on purpose. The next
        step, certification with DSC and UDIN, belongs to the CA. Sign in as
        ramesh@suntech.example to complete it.</p>
      </div>
    </div>`;
}

window.runDemo = async () => {
  const d = state.demo = { running: true, current: 0, info: {}, caseId: null, done: false };
  const set = (i, msg) => { d.current = i; d.info[i] = msg; if (location.hash === "#/demo") renderDemo(); };
  try {
    // Step 1: client and vendor
    set(0, "Checking directory");
    await loadDirectory();
    let client = state.clients.find(c => c.name === "Demo Trading Co");
    if (!client) {
      client = await api("/clients", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: "Demo Trading Co", pan: "AAADT1234D" }) });
      state.clients.push(client);
    }
    let vendor = state.vendors.find(v => v.name === "Atlas Components FZE" && v.client_id === client.id);
    if (!vendor) {
      vendor = await api("/vendors", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ client_id: client.id, name: "Atlas Components FZE", country: "United Arab Emirates" }) });
      state.vendors.push(vendor);
    }
    set(0, `${client.name} paying ${vendor.name}`);

    // Step 2: open the case
    set(1, "Opening case");
    const amount = 150000 + Math.floor(Math.random() * 200000);
    const kase = await api("/cases", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ client_id: client.id, vendor_id: vendor.id, amount: String(amount),
        currency: "AED", purpose_code: "S0101",
        remittance_date: new Date().toISOString().slice(0, 10) }) });
    d.caseId = kase.id;
    set(1, `Case ${shortId(kase.id)} opened for ${fmtAmount(amount, "AED")}`);

    // Step 3: generate and upload a sample invoice
    set(2, "Uploading generated invoice");
    const invoiceText = [
      "TAX INVOICE",
      `Invoice number INV-${Date.now()}`,
      `Supplier Atlas Components FZE, Jebel Ali Free Zone, Dubai, UAE`,
      `Buyer Demo Trading Co, Mumbai, India`,
      `Amount AED ${amount.toLocaleString("en-IN")}`,
      `Purpose Import of machine components`,
      `Date ${new Date().toDateString()}`,
    ].join("\n");
    const fd = new FormData();
    fd.append("file", new Blob([invoiceText], { type: "text/plain" }), `demo-invoice-${shortId(kase.id)}.txt`);
    fd.append("doc_type", "invoice");
    await api(`/cases/${kase.id}/documents`, { method: "POST", body: fd });
    set(2, "Invoice stored, pipeline dispatched");

    // Step 4: watch the pipeline work
    set(3, "Waiting for extraction and classification");
    const start = Date.now();
    let last = "";
    while (Date.now() - start < 90000) {
      await new Promise(r => setTimeout(r, 2500));
      const cur = await api(`/cases/${kase.id}`);
      if (cur.status !== last) { last = cur.status; set(3, `Status ${STATUS_LABELS[cur.status] || cur.status}`); }
      if (["ready_for_review", "pending_documents", "exception"].includes(cur.status)) {
        const secs = Math.round((Date.now() - start) / 1000);
        set(3, `Classified Part ${cur.part_classification || "?"} in ${secs} seconds`);
        // Step 5: arrived
        if (cur.status === "ready_for_review") {
          set(4, "The case is in the CA queue. Automation stops here by design.");
        } else if (cur.status === "pending_documents") {
          set(4, "Automation found document gaps and is chasing them. That is also a valid outcome.");
        } else {
          set(4, "Routed to human triage.");
        }
        d.done = true; d.running = false; d.current = 5;
        renderDemo();
        toast("Demo complete. Open the case to see the audit trail.", "ok");
        return;
      }
    }
    throw new Error("The pipeline did not finish in 90 seconds. Check that the worker is running.");
  } catch (e) {
    d.failed = d.current; d.running = false;
    d.info[d.current] = e.message;
    renderDemo();
    toast(e.message, "err");
  }
};

/* ---------- Settings ---------- */

async function renderSettings() {
  stopPolling();
  const [usage, system] = await Promise.all([api("/dashboard/usage"), api("/dashboard/system")]);
  const u = state.session.user, f = state.session.firm;
  const planLabel = usage.plan.replace(/^ca_/, "CA ").replace(/_/g, " ");
  const theme = document.documentElement.getAttribute("data-theme") ||
    (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");

  viewEl().innerHTML = `
    <div class="view-head"><h1>Settings</h1></div>
    <div class="settings-grid">
      <div class="card">
        <h3 class="card-title">Profile</h3>
        <div class="setting-row"><span class="sk">Name</span><span class="sv">${esc(u.name)}</span></div>
        <div class="setting-row"><span class="sk">Email</span><span class="sv">${esc(u.email)}</span></div>
        <div class="setting-row"><span class="sk">Role</span><span class="sv">${esc(u.role.replace("_", " "))}</span></div>
        <div class="setting-row"><span class="sk">Session</span>
          <button class="btn" onclick="signOutClick()">Sign out</button></div>
      </div>

      <div class="card">
        <h3 class="card-title">Workspace</h3>
        <div class="setting-row"><span class="sk">Firm</span><span class="sv">${esc(f.name)}</span></div>
        <div class="setting-row"><span class="sk">Plan</span><span class="sv">${esc(planLabel)}</span></div>
        <div class="setting-row"><span class="sk">Included remittances</span><span class="sv">${usage.included_remittances} per month</span></div>
        <div class="setting-row"><span class="sk">Used this month</span><span class="sv">${usage.used_this_month}</span></div>
        <div class="setting-row"><span class="sk">Overage rate</span><span class="sv">₹${esc(usage.overage_rate_inr)} per extra remittance</span></div>
      </div>

      <div class="card">
        <h3 class="card-title">Automation</h3>
        <div class="setting-row"><span class="sk">Pipeline driver</span><span class="sv">${esc(system.pipeline_driver)}</span></div>
        <div class="setting-row"><span class="sk">Rule set</span><span class="sv">${esc(system.rule_version)}</span></div>
        <div class="setting-row"><span class="sk">Extraction provider</span><span class="sv">${esc(system.ocr_provider)}</span></div>
        <div class="setting-row"><span class="sk">Document reminders</span><span class="sv">every ${system.reminder_interval_hours} h, ${system.reminder_max_included} included</span></div>
        <div class="setting-row"><span class="sk">Environment</span><span class="sv">${esc(system.environment)}</span></div>
      </div>

      <div class="card">
        <h3 class="card-title">Appearance</h3>
        <div class="setting-row"><span class="sk">Theme</span>
          <button class="btn" onclick="toggleTheme()">Switch to ${theme === "dark" ? "light" : "dark"}</button></div>
        <div class="setting-row"><span class="sk">Version</span><span class="sv">${esc(system.version)}</span></div>
      </div>
    </div>`;
}

window.signOutClick = () => signOut();
window.toggleTheme = () => {
  const root = document.documentElement;
  const cur = root.getAttribute("data-theme") ||
    (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
  const next = cur === "dark" ? "light" : "dark";
  root.setAttribute("data-theme", next);
  localStorage.setItem("theme", next);
  if (location.hash.startsWith("#/settings")) renderSettings();
};

/* ---------- router ---------- */

async function route() {
  if (!state.session) { showLogin(); return; }
  showApp();
  const hash = location.hash || "#/dashboard";
  const viewKey = (hash.match(/^#\/(\w+)/) || [])[1] || "dashboard";
  document.getElementById("topbar-title").textContent = VIEW_TITLES[viewKey] || "Dashboard";
  document.querySelectorAll("#nav a").forEach(a =>
    a.classList.toggle("active", hash.startsWith(a.getAttribute("href"))));
  const caseMatch = hash.match(/^#\/cases\/([0-9a-f-]{36})$/);
  try {
    if (state.clients.length === 0) await loadDirectory();
    if (caseMatch) await renderCaseDetail(caseMatch[1]);
    else if (hash.startsWith("#/invoices")) await renderInvoices();
    else if (hash.startsWith("#/cases")) await renderCases();
    else if (hash.startsWith("#/new")) await renderNewCase();
    else if (hash.startsWith("#/directory")) await renderDirectory();
    else if (hash.startsWith("#/demo")) await renderDemo();
    else if (hash.startsWith("#/settings")) await renderSettings();
    else await renderDashboard();
  } catch (e) {
    if (String(e.message).toLowerCase().includes("unauthorized")) { signOut(); return; }
    toast(e.message, "err");
  }
}

/* ---------- wiring ---------- */

document.getElementById("login-form").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const errEl = document.getElementById("login-error");
  const btn = document.getElementById("login-btn");
  errEl.classList.add("hidden");
  btn.disabled = true; btn.textContent = "Signing in";
  try {
    const res = await fetch(API + "/auth/login", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        email: document.getElementById("login-email").value.trim(),
        password: document.getElementById("login-password").value,
      }),
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail || "Sign in failed");
    }
    state.session = await res.json();
    localStorage.setItem("session", JSON.stringify(state.session));
    location.hash = "#/dashboard";
    route();
  } catch (e) {
    errEl.textContent = e.message;
    errEl.classList.remove("hidden");
  } finally {
    btn.disabled = false; btn.textContent = "Sign in";
  }
});

document.getElementById("user-menu-btn").addEventListener("click", () =>
  document.getElementById("user-dropdown").classList.toggle("hidden"));
document.addEventListener("click", (ev) => {
  if (!document.getElementById("user-menu").contains(ev.target)) {
    document.getElementById("user-dropdown").classList.add("hidden");
  }
});
document.getElementById("btn-signout").addEventListener("click", signOut);

document.getElementById("btn-certify-cancel").addEventListener("click", () =>
  document.getElementById("certify-overlay").classList.add("hidden"));

document.getElementById("btn-certify-confirm").addEventListener("click", async () => {
  const errEl = document.getElementById("certify-error");
  const dsc = document.getElementById("dsc-input").value.trim();
  const udin = document.getElementById("udin-input").value.trim();
  if (!dsc || !udin) { errEl.textContent = "DSC reference and UDIN are both required."; errEl.classList.remove("hidden"); return; }
  try {
    await api(`/cases/${state.currentCaseId}/certify`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ dsc_reference: dsc, udin, actor_user_id: state.session.user.id }),
    });
    document.getElementById("certify-overlay").classList.add("hidden");
    toast("Case certified. DSC and UDIN recorded.", "ok");
  } catch (e) {
    errEl.textContent = e.message;
    errEl.classList.remove("hidden");
  }
});

if (localStorage.getItem("theme")) {
  document.documentElement.setAttribute("data-theme", localStorage.getItem("theme"));
}

// The pilot credentials panel is a development convenience. Hide it anywhere
// other than a development environment so it never reaches a client.
fetch(API + "/meta")
  .then(r => r.ok ? r.json() : null)
  .then(meta => {
    if (meta && meta.environment !== "dev") {
      const box = document.getElementById("login-demo-box");
      if (box) box.remove();
    }
  })
  .catch(() => { /* leave the panel as is if the check fails */ });

window.addEventListener("hashchange", route);
loadSession();
route();
