/**
 * i18n core — a tiny, dependency-free locale layer.
 *
 * - Dictionary loaders are dynamic so no weight is added for inactive locales.
 * - `t(key, params)` resolves a key, interpolates `{param}` placeholders and
 *   falls back to the English dictionary (then to the raw key) when a
 *   translation is missing.
 * - `dir` is derived from the locale (Arabic → RTL).
 * - Number/date/currency formatting uses `Intl` formatters cached per locale.
 */

import en from "./en.js";
import ar from "./ar.js";

const DICTIONARIES = { en, ar };
const FALLBACK = en;

let currentLocale = "en";

function normalize(code) {
  return String(code || "").toLowerCase().split("-")[0];
}

function setLocale(code) {
  const next = DICTIONARIES[normalize(code)] ? normalize(code) : "en";
  if (next === currentLocale) return next;
  currentLocale = next;
  return currentLocale;
}

async function loadLocale(code) {
  const norm = normalize(code);
  if (norm === "en" || DICTIONARIES[norm]) return setLocale(norm);
  try {
    const module = await import(`./${norm}.js`);
    DICTIONARIES[norm] = module.default || module;
    return setLocale(norm);
  } catch {
    return setLocale("en");
  }
}

const LOCALE_KEY = "eis:lang";

/**
 * Activate a locale for the whole document: load the dictionary, set
 * `lang` + `dir` on <html> and persist the choice locally so the no-flash
 * bootstrap in index.html paints the app in the right direction.
 */
async function applyAppLocale(code, opts = {}) {
  const before = currentLocale;
  const norm = await loadLocale(code);
  if (typeof document !== "undefined" && document.documentElement) {
    document.documentElement.lang = norm;
    document.documentElement.dir = getDirection();
  }
  try {
    window.localStorage.setItem(LOCALE_KEY, norm);
  } catch {
    // Storage unavailable — the locale still applies for this session.
  }
  // Notify the shell so header/nav/breadcrumbs re-render in the new language
  // immediately (Req 5). Suppressed for in-form previews via `silent`, and
  // never fired when the locale did not actually change.
  if (norm !== before && !opts.silent && typeof window !== "undefined") {
    if (typeof window.CustomEvent === "function" && typeof window.dispatchEvent === "function") {
      try {
        window.dispatchEvent(new window.CustomEvent("eis:localechange", { detail: { locale: norm } }));
      } catch {
        // Best-effort: the locale is already applied to the document.
      }
    }
  }
  return norm;
}

function readPersistedLocale() {
  try {
    return window.localStorage.getItem(LOCALE_KEY);
  } catch {
    return null;
  }
}

/**
 * Resolve the effective locale for the current user.
 *
 * Priority (authoritative first):
 *   1. the signed-in user's profile language (backend-persisted, so it
 *      travels across devices and survives reloads),
 *   2. the device-persisted choice (`eis:lang`),
 *   3. the application default language,
 *   4. "en".
 *
 * The profile preference intentionally wins, so an Application default
 * language change never overwrites a user's explicit choice. Unknown codes
 * are left to `applyAppLocale`, which normalises them to an available
 * dictionary (currently en/ar).
 */
function resolveEffectiveLocale(prefs = {}, appSettings = {}, persisted = null) {
  const profile = normalize(prefs.language);
  if (profile) return profile;
  if (persisted) {
    const norm = normalize(persisted);
    if (norm) return norm;
  }
  const app = normalize(appSettings.default_language);
  if (app) return app;
  return "en";
}

function t(key, params) {
  const dict = DICTIONARIES[currentLocale] || FALLBACK;
  let value = dict[key];
  if (value === undefined) value = FALLBACK[key];
  if (value === undefined) return key;
  if (params && Object.keys(params).length > 0) {
    return String(value).replace(/\{(\w+)\}/g, (match, name) =>
      params[name] !== undefined ? String(params[name]) : match,
    );
  }
  return value;
}

function getLocale() {
  return currentLocale;
}

function getDirection() {
  return currentLocale === "ar" ? "rtl" : "ltr";
}

const FORMATTERS = {};

function formatter(kind, opts) {
  const signature = `${kind}\u0000${JSON.stringify(opts)}`;
  let entry = FORMATTERS[signature];
  if (!entry) {
    entry = new Intl[`${kind}Format`](currentLocale.replace(/_/g, "-"), opts);
    FORMATTERS[signature] = entry;
  }
  return entry;
}

const FIXED = (value) => {
  if (value === null || value === undefined || value === "") return "—";
  const n = Number(value);
  return Number.isFinite(n) ? String(n) : String(value);
};

const DECIMAL = (value, digits = 0) => {
  if (value === null || value === undefined || value === "") return "—";
  const n = Number(value);
  if (!Number.isFinite(n)) return String(value);
  return formatter("Number", { maximumFractionDigits: digits }).format(n);
};

const MONEY = (value, currency) => {
  if (value === null || value === undefined || value === "") return "—";
  const n = Number(value);
  if (!Number.isFinite(n)) return String(value);
  return formatter("Number", {
    style: "currency",
    currency: currency || "USD",
    maximumFractionDigits: 2,
  }).format(n);
};

const DATE = (iso) => {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return String(iso);
  return formatter("DateTimeFormat", {
    year: "numeric",
    month: "short",
    day: "numeric",
  }).format(d);
};

const DATETIME = (iso) => {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return String(iso);
  return formatter("DateTimeFormat", {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(d);
};

const TIME = (iso) => {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return String(iso);
  return formatter("DateTimeFormat", {
    hour: "2-digit",
    minute: "2-digit",
  }).format(d);
};

export {
  loadLocale,
  setLocale,
  getLocale,
  getDirection,
  applyAppLocale,
  readPersistedLocale,
  resolveEffectiveLocale,
  t,
  FIXED,
  DECIMAL,
  MONEY,
  DATE,
  DATETIME,
  TIME,
};