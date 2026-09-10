/**
 * Accounting file import workflow. Uploads a CSV/XLSX file to
 * POST /api/imports (multipart `file` field), streams progress via XHR and
 * shows the full import outcome, then offers the natural next step.
 */

import { el, clear, qs } from "../utils/dom.js";
import { LIMITS, ACCEPTED_UPLOAD_EXTENSIONS } from "../config.js";
import { uploadImport } from "../services/imports.js";
import { importErrorLabel, batchStatusLabel, formatNumber } from "../utils/format.js";
import { escapeHtml } from "../utils/escape.js";
import { unwrapImportResult } from "../utils/payload.js";
import { toast } from "../components/toast.js";

const BATCH_KEY = "eis.recent_batches";

function recentBatches() {
  try {
    return JSON.parse(window.localStorage.getItem(BATCH_KEY) || "[]");
  } catch {
    return [];
  }
}

function rememberBatch(batch) {
  const list = recentBatches().filter((id) => id !== batch.id);
  list.unshift(batch.id);
  window.localStorage.setItem(BATCH_KEY, JSON.stringify(list.slice(0, 20)));
}

export async function renderImports(container) {
  clear(container);
  document.body.classList.remove("login-body");

  container.appendChild(
    el("div", { className: "page-head" },
      el("div", null,
        el("h1", { className: "page-title" }, "Accounting file import"),
        el("div", { className: "page-head__meta" }, "Upload a CSV or Excel file of accounting invoices. One row per line item."),
      ),
    ),
  );

  container.appendChild(buildUploadCard());

  const recentBox = el("div", { className: "card", style: "margin-block-start:1.25rem;" });
  container.appendChild(recentBox);
  renderRecent(recentBox);
}

function buildUploadCard() {
  const card = el("div", { className: "card" });
  card.appendChild(
    el("div", { className: "card__header" },
      el("div", { className: "section-title" }, "Upload accounting file"),
      el("span", { className: "text-xs text-muted" }, "CSV or XLSX · max 10 MB"),
    ),
  );

  const body = el("div", { className: "card__body" });
  card.appendChild(body);

  // ---- Step 1: select file ----
  const fileInput = el("input", {
    type: "file",
    id: "import-file",
    accept: ACCEPTED_UPLOAD_EXTENSIONS.join(","),
    className: "input",
    style: "display:none;",
  });

  const fileName = el("div", { className: "text-sm text-secondary", "aria-live": "polite" }, "No file selected");
  const dropzone = el("div", {
    className: "dropzone",
    tabindex: "0",
    role: "button",
    "aria-label": "Choose a CSV or XLSX file to import",
  },
    el("div", { className: "dropzone__title" }, "Choose a CSV or Excel file, or drop it here"),
    el("div", { className: "text-xs" }, "Accepted: .csv, .xlsx · one row per invoice line item"),
  );
  dropzone.addEventListener("click", () => fileInput.click());
  dropzone.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); fileInput.click(); } });
  dropzone.addEventListener("dragover", (e) => { e.preventDefault(); dropzone.classList.add("is-dragover"); });
  dropzone.addEventListener("dragleave", () => dropzone.classList.remove("is-dragover"));
  dropzone.addEventListener("drop", (e) => {
    e.preventDefault();
    dropzone.classList.remove("is-dragover");
    if (e.dataTransfer.files.length) setFile(e.dataTransfer.files[0]);
  });

  fileInput.addEventListener("change", () => {
    if (fileInput.files.length) setFile(fileInput.files[0]);
  });

  const meta = el("div", null,
    dropzone,
    el("div", { className: "text-sm text-secondary", style: "margin-block-start:0.75rem;" }, fileName),
  );

  // ---- Step 2: upload button + progress ----
  const uploadBtn = el("button", { className: "btn btn-primary", type: "button", disabled: "disabled" }, "Upload and import");
  const progressWrap = el("div", null);
  progressWrap.style.display = "none";

  const summaryBox = el("div");
  const errorsBox = el("div");

  let selected = null;

  function setFile(file) {
    selected = file;
    const ext = file.name.slice(file.name.lastIndexOf(".")).toLowerCase();
    const fileOk = ACCEPTED_UPLOAD_EXTENSIONS.includes(ext) || /\.(csv|xlsx)$/i.test(file.name);
    const sizeOk = file.size <= LIMITS.maxUploadBytes;
    const ok = fileOk && sizeOk;

    fileName.textContent = `${file.name} (${formatFileSize(file.size)})`;
    fileName.classList.toggle("neg", !ok);
    uploadBtn.disabled = !ok;

    let reason = "";
    if (!fileOk) reason = "Unsupported file type — choose a .csv or .xlsx file.";
    if (fileOk && !sizeOk) reason = "File exceeds the 10 MB limit.";
    meta.appendChild(replaceHint(meta, reason));
  }

  function replaceHint(scope, text) {
    const existing = qs(".import-hint", scope);
    if (existing) existing.remove();
    if (!text) return existing;
    const h = el("div", { className: "import-hint alert alert--warning text-xs", style: "margin-block-start:0.5rem;", role: "status" }, text);
    scope.appendChild(h);
    return h;
  }

  uploadBtn.addEventListener("click", async () => {
    if (!selected) return;
    uploadBtn.disabled = true;
    fileName.textContent = "Uploading…";

    const form = new FormData();
    form.append("file", selected);

    progressWrap.style.display = "block";
    progressWrap.appendChild(el("div", { className: "progress-track" },
      el("div", { className: "progress-bar is-indeterminate", role: "progressbar", "aria-label": "Uploading and importing" }),
    ));

    try {
      // Backend POST /api/imports returns {batch, errors} under data; keep a
      // direct-batch fallback for resilience.
      const result = await uploadImport(form);
      progressWrap.style.display = "none";
      uploadBtn.disabled = true;
      const batch = unwrapImportResult(result);
      rememberBatch(batch);
      toast("Import completed", { type: "success" });
      renderOutcome(summaryBox, errorsBox, batch);
      window.setTimeout(() => {
        if (batch.id) window.location.hash = `#/imports/${batch.id}`;
      }, 900);
    } catch (err) {
      progressWrap.style.display = "none";
      uploadBtn.disabled = false;
      fileName.textContent = "Upload failed. Choose a file to retry.";
      const message = err.message || "Import failed — please check the file and try again.";
      toast(message, { type: "error" });
      summaryBox.replaceChildren(el("div", { className: "alert alert--error" }, message));
    }
  });

  body.appendChild(el("div", { className: "form-field" },
    meta,
    el("div", { className: "form-actions" }, uploadBtn, progressWrap),
  ));
  body.appendChild(summaryBox);
  body.appendChild(errorsBox);

  return card;
}

function renderOutcome(summaryBox, errorsBox, batch) {
  clear(summaryBox);
  clear(errorsBox);

  const rows = [
    ["Batch", escapeHtml(String(batch.id))],
    ["File", escapeHtml(batch.filename || "—")],
    ["Status", batchStatusLabel(batch.status)],
    ["Total rows", formatNumber(batch.total_rows)],
    ["Processed rows", formatNumber(batch.processed_rows)],
    ["Rejected rows", formatNumber(batch.error_rows)],
  ];

  summaryBox.appendChild(
    el("div", { className: "card", style: "margin-block-start:1.25rem;" },
      el("div", { className: "card__header" },
        el("div", { className: "section-title" }, "Import result"),
        el("span", { className: `badge badge--${batch.status}` }, batchStatusLabel(batch.status)),
      ),
      el("div", { className: "card__body" },
        el("dl", { className: "dl" }, ...rows.map(([k, v]) => el("div", null, el("dt", null, k), el("dd", null, v)))),
      ),
    ),
  );
}

async function renderRecent(container) {
  clear(container);
  container.appendChild(
    el("div", { className: "card__header" },
      el("div", { className: "section-title" }, "Recent imports"),
      el("span", { className: "text-xs text-muted" }, "Batches imported from this session"),
    ),
  );

  const ids = recentBatches();
  if (ids.length === 0) {
    container.appendChild(el("div", { className: "etable-empty" }, "No imports from this session yet."));
    return;
  }

  const list = el("ul", { className: "list-plain" });
  for (const id of ids) {
    const item = el("li", { style: "padding:0.5rem 1rem;border-block-end:1px solid var(--color-border);" },
      el("button", { className: "btn btn-ghost btn-sm", onClick: () => { window.location.hash = `#/imports/${id}`; } },
        `Batch #${id}`),
    );
    list.appendChild(item);
  }
  container.appendChild(el("div", { className: "card__body" }, list));
}

function formatFileSize(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}