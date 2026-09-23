/**
 * Accounting file import workflow. Uploads a CSV/XLSX file to
 * POST /api/imports (multipart `file` field), streams progress via XHR and
 * shows the full import outcome, then offers the natural next step.
 */

import { el, clear, qs, icons } from "../utils/dom.js";
import { LIMITS, ACCEPTED_UPLOAD_EXTENSIONS } from "../config.js";
import { uploadImport } from "../services/imports.js";
import { importErrorLabel, batchStatusLabel, statusClassToken, formatNumber } from "../utils/format.js";
import { unwrapImportResult } from "../utils/payload.js";
import { toast } from "../components/toast.js";
import { t } from "../i18n/index.js";

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
        el("h1", { className: "page-title" }, t("imports.title")),
        el("div", { className: "page-head__meta" }, t("imports.meta")),
      ),
    ),
  );

  container.appendChild(buildUploadCard());

  const recentBox = el("div", { className: "card" });
  container.appendChild(recentBox);
  renderRecent(recentBox);
}

function buildUploadCard() {
  const card = el("div", { className: "card" });
  card.appendChild(
    el("div", { className: "card__header" },
      el("div", { className: "section-title" }, t("imports.uploadCard")),
      el("span", { className: "text-xs text-muted" }, t("imports.formatHint", { size: formatFileSize(LIMITS.maxUploadBytes) })),
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

  const fileName = el("div", { className: "text-sm text-secondary", "aria-live": "polite" }, t("imports.noFile"));
  const dropzone = el("div", {
    className: "dropzone",
    tabindex: "0",
    role: "button",
    "aria-label": t("imports.chooseAria"),
  },
    el("div", { className: "dropzone__icon" }, (() => { const ic = icons.import.cloneNode(true); ic.setAttribute("aria-hidden", "true"); return ic; })()),
    el("div", { className: "dropzone__title" }, t("imports.chooseTitle")),
    el("div", { className: "text-xs" }, t("imports.accepted")),
  );
  dropzone.addEventListener("click", () => fileInput.click());
  dropzone.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); fileInput.click(); } });

  // Drag counter keeps the highlight stable while dragging over child nodes.
  let dragDepth = 0;
  dropzone.addEventListener("dragenter", (e) => { e.preventDefault(); dragDepth += 1; dropzone.classList.add("is-dragover"); });
  dropzone.addEventListener("dragover", (e) => { e.preventDefault(); });
  dropzone.addEventListener("dragleave", () => { dragDepth -= 1; if (dragDepth <= 0) { dragDepth = 0; dropzone.classList.remove("is-dragover"); } });
  dropzone.addEventListener("drop", (e) => {
    e.preventDefault();
    dragDepth = 0;
    dropzone.classList.remove("is-dragover");
    if (e.dataTransfer.files.length) setFile(e.dataTransfer.files[0]);
  });

  fileInput.addEventListener("change", () => {
    if (fileInput.files.length) setFile(fileInput.files[0]);
  });

  const meta = el("div", null,
    dropzone,
    el("div", { className: "text-sm text-secondary", style: "margin-block-start:var(--space-3);" }, fileName),
  );

  // ---- Step 2: upload button + progress ----
  const uploadBtn = el("button", { className: "btn btn-primary", type: "button", disabled: "disabled" }, t("imports.upload"));
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
    if (!fileOk) reason = t("imports.unsupported");
    if (fileOk && !sizeOk) reason = t("imports.exceeds", { size: formatFileSize(LIMITS.maxUploadBytes) });
    meta.appendChild(replaceHint(meta, reason));
  }

  function replaceHint(scope, text) {
    const existing = qs(".import-hint", scope);
    if (existing) existing.remove();
    if (!text) return existing;
    const h = el("div", { className: "import-hint alert alert--warning text-xs", style: "margin-block-start:var(--space-2);", role: "status" }, text);
    scope.appendChild(h);
    return h;
  }

  uploadBtn.addEventListener("click", async () => {
    if (!selected) return;
    uploadBtn.disabled = true;
    fileName.textContent = t("imports.uploading");

    const form = new FormData();
    form.append("file", selected);

    progressWrap.style.display = "block";
    progressWrap.appendChild(el("div", { className: "progress-track" },
      el("div", { className: "progress-bar is-indeterminate", role: "progressbar", "aria-label": t("imports.progressAria") }),
    ));

    try {
      // Backend POST /api/imports returns {batch, errors} under data; keep a
      // direct-batch fallback for resilience.
      const result = await uploadImport(form);
      progressWrap.style.display = "none";
      uploadBtn.disabled = true;
      const batch = unwrapImportResult(result);
      rememberBatch(batch);
      toast(t("imports.completed"), { type: "success" });
      renderOutcome(summaryBox, errorsBox, batch);
      window.setTimeout(() => {
        if (batch.id) window.location.hash = `#/imports/${batch.id}`;
      }, 900);
    } catch (err) {
      progressWrap.style.display = "none";
      uploadBtn.disabled = false;
      fileName.textContent = t("imports.uploadFailed");
      const message = err.message || t("imports.importFailed");
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
    [t("imports.batch"), String(batch.id)],
    [t("imports.file"), batch.filename || "—"],
    [t("imports.status"), batchStatusLabel(batch.status)],
    [t("imports.totalRows"), formatNumber(batch.total_rows)],
    [t("imports.processedRows"), formatNumber(batch.processed_rows)],
    [t("imports.rejectedRows"), formatNumber(batch.error_rows)],
  ];

  summaryBox.appendChild(
    el("div", { className: "card" },
      el("div", { className: "card__header" },
        el("div", { className: "section-title" }, t("imports.result")),
        el("span", { className: `badge badge--${statusClassToken(batch.status)}` }, batchStatusLabel(batch.status)),
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
      el("div", { className: "section-title" }, t("imports.recent")),
      el("span", { className: "text-xs text-muted" }, t("imports.sessionBatches")),
    ),
  );

  const ids = recentBatches();
  if (ids.length === 0) {
    container.appendChild(el("div", { className: "state-block" },
      el("div", { className: "state-block__icon" }, "📋"),
      el("div", { className: "state-block__title" }, t("imports.noImports")),
    ));
    return;
  }

  const list = el("ul", { className: "list-plain" });
  for (const id of ids) {
    const item = el("li", { style: "padding:var(--space-2) var(--space-4);border-block-end:1px solid var(--color-border);" },
      el("button", { className: "btn btn-ghost btn-sm", onClick: () => { window.location.hash = `#/imports/${id}`; } },
        t("imports.batchNo", { id })),
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