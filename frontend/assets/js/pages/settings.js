/**
 * Settings — sections are routable sub-pages under the hash router.
 *
 * Sections (● = admin-only):
 *   ● General               application identity + non-personal defaults
 *   ● Organization          company / tax profile
 *   ● Email & Notifications SMTP status + test delivery
 *     Appearance            personal theme
 *     Language & Regional   personal language / format / timezone
 *
 * Profile identity and password management live on the standalone Account
 * page (#/account); Settings deliberately does not duplicate them.
 *
 * The active section is derived from the route (`#/settings/general`,
 * `#/settings/regional`, …) so direct navigation, refresh and the sidebar /
 * breadcrumbs stay in sync. Only the active section is mounted. Backed by the
 * existing /api/settings endpoints — no new backend surface is introduced.
 */

import { el, clear, showLoading, showError } from "../utils/dom.js";
import { getCurrentRole } from "../auth/store.js";
import { toast } from "../components/toast.js";
import {
  getApplicationSettings,
  updateApplicationSettings,
  getCompanySettings,
  updateCompanySettings,
  getUserSettings,
  updateUserSettings,
} from "../services/settings.js";
import { getEmailStatus, sendTestEmail } from "../services/email.js";
import { isValidEmail } from "../utils/validation.js";
import { setThemePreference, syncThemeFromSettings } from "../theme.js";
import { invalidateSettings, loadAppSettings, loadUserPrefs } from "../settings/store.js";
import { applyAppLocale, t } from "../i18n/index.js";

// Only locales with a shipped dictionary (i18n/en.js, i18n/ar.js) are offered:
// any other selection would persist on the backend but silently render English.
const LANGUAGES = ["en", "ar"].map((code) => ({ value: code, label: () => t(`languages.${code}`) }));
// A user's explicit choice may additionally follow the operating system.
const USER_THEMES = [
  { value: "light", label: () => t("settings.light") },
  { value: "dark", label: () => t("settings.dark") },
  { value: "system", label: () => t("settings.system") },
];
const DATE_FORMATS = ["YYYY-MM-DD", "DD/MM/YYYY", "MM/DD/YYYY", "DD-MM-YYYY"];
const NUMBER_FORMATS = ["#,##0.00", "#,##0", "0,00", "0.00"];
const TIMEZONES = ["UTC", "Africa/Cairo", "Europe/London", "Europe/Berlin", "America/New_York", "Asia/Riyadh"];

// Settings sections, in display order. `admin: true` hides the section from
// non-admins. `label` is the i18n key shared by the nav item and the card.
const SECTION_NAV = [
  { id: "general", label: "settings.navGeneral", admin: true },
  { id: "organization", label: "settings.navOrganization", admin: true },
  { id: "email", label: "settings.navEmail", admin: true },
  { id: "appearance", label: "settings.navAppearance", admin: false },
  { id: "regional", label: "settings.navRegional", admin: false },
];

const SECTION_META = {
  general: "settings.generalMeta",
  organization: "settings.organizationMeta",
  email: "settings.emailMeta",
  appearance: "settings.appearanceMeta",
  regional: "settings.regionalMeta",
};

// Notification workflow identifiers stay untranslated; their descriptions
// resolve through i18n keys when a known id is present.
const WORKFLOW_LABELS = {
  "reconciliation.discrepancies": "settings.workflowReconciliation",
};

let pageContainer = null;
let pageRoot = null;
let activeSection = null;
let isAdmin = false;

export async function renderSettings(container, params = []) {
  clear(container);
  document.body.classList.remove("login-body");

  const role = getCurrentRole();
  isAdmin = role === "admin";
  const available = SECTION_NAV.filter((s) => !s.admin || isAdmin);

  // The active section is route-driven (#/settings/:section). Unknown or
  // admin-gated sections fall back to the first section the role may see;
  // a requested-but-forbidden section redirects to that default.
  const requested = (params && params[0] && String(params[0]).toLowerCase()) || "";
  const candidate = SECTION_NAV.find((s) => s.id === requested);
  if (requested && (!candidate || (candidate.admin && !isAdmin))) {
    const fallback = (available[0] && available[0].id) || "appearance";
    if (window.location.hash !== `#/settings/${fallback}`) {
      window.location.hash = `#/settings/${fallback}`;
    }
    activeSection = fallback;
  } else {
    activeSection = allowedSection(requested, available);
  }
  pageContainer = container;
  pageRoot = null;

  container.appendChild(
    el("div", { className: "page-head" },
      el("div", null,
        el("h1", { className: "page-title" }, t("settings.title")),
        el("div", { className: "page-head__meta" }, t("settings.meta")),
      ),
    ),
  );

  const layout = el("div", { className: "settings-layout" });
  layout.appendChild(buildSettingsNav(available));
  pageRoot = el("div", { className: "settings-content" });
  layout.appendChild(pageRoot);
  container.appendChild(layout);

  await renderSection(activeSection);
}

function allowedSection(requested, available) {
  if (available.some((s) => s.id === requested)) return requested;
  return (available[0] && available[0].id) || "appearance";
}

/** Map a settings sub-route id to its i18n label key (used for breadcrumbs). */
export function settingsSectionKey(id) {
  const section = SECTION_NAV.find((s) => s.id === id);
  return section ? section.label : null;
}

/** Reset the page-level navigation state (used on sign-out / in tests). */
export function resetSettingsView() {
  activeSection = null;
  pageContainer = null;
  pageRoot = null;
  isAdmin = false;
}

function buildSettingsNav(available) {
  const nav = el("nav", { className: "settings-nav", "aria-label": t("settings.navLabel") });
  for (const section of available) {
    nav.appendChild(
      el("a", {
        className: `settings-nav__item${section.id === activeSection ? " is-active" : ""}`,
        href: `#/settings/${section.id}`,
        "aria-current": section.id === activeSection ? "page" : undefined,
        dataset: { section: section.id },
      }, t(section.label)),
    );
  }
  return nav;
}

async function renderSection(id) {
  clear(pageRoot);
  const section = SECTION_NAV.find((s) => s.id === id);
  const heading = { title: t(section.label), meta: t(SECTION_META[id] || "") };
  const mount = {
    general: mountGeneralSection,
    organization: mountOrganizationSection,
    email: mountEmailSection,
    appearance: mountAppearanceSection,
    regional: mountRegionalSection,
  }[id];
  await mount(pageRoot, heading);
}

/* ----------------------------- Shared bits ---------------------------- */

function sectionCard({ title, meta }) {
  const card = el("div", { className: "card" });
  card.appendChild(
    el("div", { className: "card__header" },
      el("div", null,
        el("div", { className: "section-title" }, title),
        meta ? el("div", { className: "text-sm text-secondary", style: "margin-block-start:var(--space-1);" }, meta) : null,
      ),
    ),
  );
  const body = el("div", { className: "card__body" });
  card.appendChild(body);
  return { card, body };
}

/* ----------------------------- General (app) --------------------------- */

async function mountGeneralSection(root, heading) {
  const { card, body } = sectionCard(heading);
  root.appendChild(card);

  showLoading(body, t("settings.loadingApp"));
  let data;
  try {
    data = await getApplicationSettings();
  } catch (err) {
    showError(body, err.message || t("settings.failedApp"), { onRetry: () => { clear(root); mountGeneralSection(root, heading); } });
    return;
  }
  clear(body);

  const form = buildAppForm(data);
  body.appendChild(form);

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const payload = readAppForm(form);
    try {
      const saved = await updateApplicationSettings(payload);
      applyValues(form, saved);
      // Refresh the cached app settings so the shell/sidebar and theme engine
      // see the new defaults immediately — no page reload required.
      invalidateSettings();
      await loadAppSettings(true);
      syncThemeFromSettings();
      toast(t("settings.savedApp"), { type: "success" });
    } catch (err) {
      showFormError(form, err.message || t("settings.failedSaveApp"));
    }
  });
}

function buildAppForm(data) {
  // Application identity + defaults for new accounts. Language and theme
  // defaults are owned by Language & Regional / Appearance, not General.
  const fields = [
    ["application_name", t("settings.labelAppName"), "text", data.application_name || ""],
    ["application_subtitle", t("settings.labelSubtitle"), "text", data.application_subtitle || ""],
    ["date_format", t("settings.labelDefaultDateFormat"), "select", data.date_format || "YYYY-MM-DD", DATE_FORMATS],
    ["number_format", t("settings.labelDefaultNumberFormat"), "select", data.number_format || "#,##0.00", NUMBER_FORMATS],
    ["timezone", t("settings.labelDefaultTimezone"), "select", data.timezone || "UTC", TIMEZONES],
  ];
  const grid = el("div", { className: "form-grid form-grid__2col" }, ...fields.map((f) => fieldInput(...f)));
  return el("form", null, grid, el("div", { className: "form-actions" },
    el("button", { className: "btn btn-primary", type: "submit" }, t("settings.saveApp"))));
}

/* --------------------------- Organization (company) -------------------- */

async function mountOrganizationSection(root, heading) {
  const { card, body } = sectionCard(heading);
  root.appendChild(card);

  showLoading(body, t("settings.loadingCompany"));
  let data;
  try {
    data = await getCompanySettings();
  } catch (err) {
    showError(body, err.message || t("settings.failedCompany"), { onRetry: () => { clear(root); mountOrganizationSection(root, heading); } });
    return;
  }
  clear(body);

  const form = buildCompanyForm(data);
  body.appendChild(form);

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const payload = readCompanyForm(form);
    payload.default_tax_rate = parseFloat(payload.default_tax_rate) || 0;
    try {
      const saved = await updateCompanySettings(payload);
      applyValues(form, saved);
      toast(t("settings.savedCompany"), { type: "success" });
    } catch (err) {
      showFormError(form, err.message || t("settings.failedSaveCompany"));
    }
  });
}

function buildCompanyForm(data) {
  const fields = [
    ["name", t("settings.labelCompanyName"), "text", data.name || ""],
    ["tax_registration_number", t("settings.labelTaxReg"), "text", data.tax_registration_number || ""],
    ["email", t("settings.labelBillingEmail"), "email", data.email || ""],
    ["phone", t("settings.labelPhone"), "text", data.phone || ""],
    ["address", t("settings.labelAddress"), "textarea", data.address || ""],
    ["website", t("settings.labelWebsite"), "url", data.website || ""],
    ["default_currency", t("settings.labelCurrency"), "text", data.default_currency || "EGP", null, { maxlength: 3, style: "text-transform:uppercase;" }],
    ["default_tax_rate", t("settings.labelTaxRate"), "number", data.default_tax_rate ?? 0, null, { min: 0, max: 100, step: "0.01" }],
    ["fiscal_year_start", t("settings.labelFiscalYear"), "text", data.fiscal_year_start || "01-01", null, { maxlength: 5 }],
  ];
  const grid = el("div", { className: "form-grid form-grid__2col" }, ...fields.map((f) => fieldInput(...f)));
  return el("form", null, grid, el("div", { className: "form-actions" },
    el("button", { className: "btn btn-primary", type: "submit" }, t("settings.saveCompany"))));
}

/* ------------------------------ Appearance ----------------------------- */

async function mountAppearanceSection(root, heading) {
  const { card, body } = sectionCard(heading);
  root.appendChild(card);

  showLoading(body, t("settings.loadingProfile"));
  let data;
  try {
    data = await getUserSettings();
  } catch (err) {
    showError(body, err.message || t("settings.failedProfile"), { onRetry: () => { clear(root); mountAppearanceSection(root, heading); } });
    return;
  }
  clear(body);

  // Personal theme (available to every user). The label and hint make clear
  // this is the single per-account theme control.
  const form = el("form", null,
    el("div", { className: "form-grid form-grid__2col" },
      fieldInput("theme", t("settings.labelPersonalTheme"), "select", data.theme || "light", USER_THEMES, null, t("settings.themePersonalHint"))),
    el("div", { className: "form-actions" },
      el("button", { className: "btn btn-primary", type: "submit" }, t("settings.saveProfile"))),
  );
  body.appendChild(form);

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const raw = value(form, "theme");
    if (!raw) return;
    // "system" is a frontend-only choice (the server only persists
    // light/dark), so it is applied locally and omitted from the payload.
    const payload = raw === "system" ? null : { theme: raw };
    try {
      if (payload) {
        const saved = await updateUserSettings(payload);
        applyValues(form, saved);
        await loadUserPrefs(true);
      }
      setThemePreference(raw);
      toast(t("settings.savedProfile"), { type: "success" });
    } catch (err) {
      showFormError(form, err.message || t("settings.failedSaveProfile"));
    }
  });
}

/* --------------------------- Language & Regional ----------------------- */

async function mountRegionalSection(root, heading) {
  const { card, body } = sectionCard(heading);
  root.appendChild(card);

  showLoading(body, t("settings.loadingProfile"));
  let data;
  try {
    data = await getUserSettings();
  } catch (err) {
    showError(body, err.message || t("settings.failedProfile"), { onRetry: () => { clear(root); mountRegionalSection(root, heading); } });
    return;
  }
  clear(body);

  // Personal language / regional formatting (every user). On save the chosen
  // language is applied via applyAppLocale, which dispatches eis:localechange
  // so the app shell and this section rebuild immediately — no page reload.
  const form = buildRegionalForm(data);
  body.appendChild(form);

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const payload = readRegionalForm(form);
    try {
      const saved = await updateUserSettings(payload);
      applyValues(form, saved);
      // Refresh cached prefs before switching so the app-shell reconcile sees
      // the newly saved profile language and does not flip back to the
      // previously persisted one.
      await loadUserPrefs(true);
      // May dispatch eis:localechange → the app rebuilds the shell and this
      // section immediately in the new language (no page reload).
      await applyAppLocale(payload.language);
      toast(t("settings.savedProfile"), { type: "success" });
    } catch (err) {
      showFormError(form, err.message || t("settings.failedSaveProfile"));
    }
  });
}

function buildRegionalForm(data) {
  const fields = [
    ["language", t("settings.labelPersonalLanguage"), "select", data.language || "en", LANGUAGES, null, t("settings.languagePersonalHint")],
    ["date_format", t("settings.labelDateFormat"), "select", data.date_format || "YYYY-MM-DD", DATE_FORMATS],
    ["number_format", t("settings.labelNumberFormat"), "select", data.number_format || "#,##0.00", NUMBER_FORMATS],
    ["timezone", t("settings.labelTimezone"), "select", data.timezone || "UTC", TIMEZONES],
  ];
  const grid = el("div", { className: "form-grid form-grid__2col" }, ...fields.map((f) => fieldInput(...f)));
  return el("form", null, grid, el("div", { className: "form-actions" },
    el("button", { className: "btn btn-primary", type: "submit" }, t("settings.saveProfile"))));
}

/* ------------------------- Email & Notifications ------------------------ */

async function mountEmailSection(root, heading) {
  const { card, body } = sectionCard(heading);
  root.appendChild(card);

  showLoading(body, t("settings.loadingEmail"));
  let data;
  try {
    data = await getEmailStatus();
  } catch (err) {
    showError(body, err.message || t("settings.failedEmail"), { onRetry: () => { clear(root); mountEmailSection(root, heading); } });
    return;
  }
  clear(body);

  const enabled = Boolean(data && data.enabled);

  body.appendChild(
    el("div", { className: `alert alert--${enabled ? "success" : "warning"}`, role: "status", style: "margin-block-end:var(--space-4);" },
      enabled
        ? t("settings.emailEnabled")
        : t("settings.emailDisabled")),
  );

  body.appendChild(
    el("dl", { className: "dl" },
      el("div", null, el("dt", null, t("settings.dlProvider")), el("dd", valueOrDash(data.provider))),
      el("div", null, el("dt", null, t("settings.dlSmtp")), el("dd", hostPort(data.host, data.port))),
      el("div", null, el("dt", null, t("settings.dlFrom")), el("dd", valueOrDash(data.from_addr))),
      el("div", null, el("dt", null, t("settings.dlSecurity")), el("dd", connectionLabel(data.use_tls, data.use_ssl))),
    ),
  );

  const workflows = Array.isArray(data.workflows) ? data.workflows : [];
  if (workflows.length > 0) {
    body.appendChild(
      el("div", { style: "margin-block-start:var(--space-4);" },
        el("div", { className: "text-sm", style: "margin-block-end:var(--space-2);font-weight:700;" }, t("settings.notificationsTitle")),
        ...workflows.map((ev) =>
          el("div", { className: "text-sm text-secondary", style: "margin-block-end:var(--space-1);" },
            el("span", { className: "mono" }, ev.name || "—"), " — ", workflowDescription(ev),
          )),
      ),
    );
  }

  body.appendChild(
    el("p", { className: "text-sm text-secondary", style: "margin-block-start:var(--space-3);" },
      t("settings.emailWorkflow")),
  );

  body.appendChild(buildEmailTestForm(enabled));
}

function workflowDescription(workflow) {
  const key = workflow && workflow.name && WORKFLOW_LABELS[workflow.name];
  return key ? t(key) : (workflow.description || "");
}

function buildEmailTestForm(enabled) {
  const errBox = el("div");
  const okBox = el("div");
  const hintId = "email-test-disabled-hint";
  const disabledHelp = enabled ? undefined : t("settings.enableEmailToTest");
  const input = el("input", {
    className: "input",
    id: "email-test-to",
    name: "to",
    type: "email",
    placeholder: t("settings.testEmailPlaceholder"),
    autocomplete: "off",
    disabled: enabled ? undefined : "",
    // Non-breaking help for the disabled control: hover/focus title plus an
    // aria-describedby reference to the hint rendered below (Req 1).
    title: disabledHelp,
    "aria-describedby": enabled ? undefined : hintId,
  });
  const submitBtn = el("button", {
    className: "btn btn-primary",
    type: "submit",
    disabled: enabled ? undefined : "",
    "aria-disabled": enabled ? undefined : "true",
    title: disabledHelp,
  }, t("settings.sendTest"));

  const form = el("form", { onsubmit: (e) => { e.preventDefault(); submit(); } },
    el("div", { className: "field" },
      el("label", { for: "email-test-to" }, t("settings.testEmailLabel")),
      input,
    ),
    errBox,
    okBox,
    el("div", { className: "form-actions" }, submitBtn),
  );

  if (!enabled) {
    errBox.appendChild(el("div", { className: "alert alert--info", id: hintId },
      t("settings.enableEmailToTest")));
  }

  async function submit() {
    clear(errBox);
    clear(okBox);
    const to = input.value.trim();
    if (!isValidEmail(to)) {
      errBox.appendChild(el("div", { className: "alert alert--error" }, t("common.validEmail")));
      return;
    }
    submitBtn.disabled = true;
    submitBtn.textContent = t("settings.sending");
    try {
      const outcome = await sendTestEmail(to);
      input.value = "";
      const requestId = outcome && outcome.request_id ? ` ${t("settings.testRequestId", { id: outcome.request_id })}` : "";
      okBox.appendChild(el("div", { className: "alert alert--success" }, `${t("settings.testEmailSent")}${requestId}`));
      toast(t("settings.testSentToast"), { type: "success" });
    } catch (err) {
      errBox.appendChild(el("div", { className: "alert alert--error" }, err.message || t("settings.testFailed")));
    } finally {
      if (enabled) {
        submitBtn.disabled = false;
        submitBtn.textContent = t("settings.sendTest");
      }
    }
  }

  return form;
}

function valueOrDash(value) {
  const v = value === null || value === undefined || value === "" ? null : String(value);
  return v === null ? el("span", { className: "text-muted" }, "—") : v;
}

function hostPort(host, port) {
  if (!host) return el("span", { className: "text-muted" }, "—");
  if (port === null || port === undefined || port === "") return String(host);
  return `${host}:${port}`;
}

function connectionLabel(useTls, useSsl) {
  if (useSsl) return t("settings.connectionSsl");
  if (useTls) return t("settings.connectionStarttls");
  return t("settings.connectionNone");
}

/* ----------------------------- Helpers ----------------------------- */

function fieldInput(name, label, type, value, options = null, extra = null, hint = null) {
  const field = el("div", { className: "field" });
  field.appendChild(el("label", { for: name }, label));
  const attrs = { id: name, name, type, value: value == null ? "" : String(value), ...(extra || {}) };
  if (type === "select") {
    attrs.className = "select";
    const sel = el("select", attrs, ...(options || []).map((o) =>
      typeof o === "string"
        ? el("option", { value: o }, o)
        : el("option", { value: o.value }, typeof o.label === "function" ? o.label() : o.label)));
    sel.value = String(value == null ? "" : value);
    field.appendChild(sel);
  } else if (type === "textarea") {
    attrs.className = "textarea";
    const ta = el("textarea", attrs);
    ta.textContent = String(value == null ? "" : value);
    field.appendChild(ta);
  } else {
    attrs.className = "input";
    field.appendChild(el("input", attrs));
  }
  if (hint) field.appendChild(el("div", { className: "form-hint" }, hint));
  return field;
}

function readAppForm(root) {
  const f = root;
  return {
    application_name: value(f, "application_name"),
    application_subtitle: value(f, "application_subtitle"),
    date_format: value(f, "date_format"),
    number_format: value(f, "number_format"),
    timezone: value(f, "timezone"),
  };
}

function readCompanyForm(root) {
  const f = root;
  return {
    name: value(f, "name"),
    tax_registration_number: value(f, "tax_registration_number"),
    email: value(f, "email"),
    phone: value(f, "phone"),
    address: value(f, "address"),
    website: value(f, "website"),
    default_currency: value(f, "default_currency"),
    default_tax_rate: value(f, "default_tax_rate"),
    fiscal_year_start: value(f, "fiscal_year_start"),
  };
}

function readRegionalForm(root) {
  const f = root;
  return {
    language: value(f, "language"),
    date_format: value(f, "date_format"),
    number_format: value(f, "number_format"),
    timezone: value(f, "timezone"),
  };
}

function value(form, name) {
  const node = form.querySelector(`[name="${name}"]`);
  return node ? node.value : "";
}

function applyValues(root, saved) {
  const form = root;
  for (const [key, val] of Object.entries(saved || {})) {
    const node = form.querySelector(`[name="${key}"]`);
    if (node && val !== null && val !== undefined) node.value = String(val);
  }
}

function showFormError(root, message) {
  const form = root;
  removeError(form);
  const err = el("div", { className: "alert alert--error", style: "margin-block:var(--space-3);" }, message);
  form.prepend(err);
}

function removeError(form) {
  const existing = form.querySelector(".alert--error");
  if (existing) existing.remove();
}