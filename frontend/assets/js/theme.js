/**
 * Theme Engine — the single source of truth for the application theme.
 *
 * Canonical preference is one of: "light" | "dark" | "system".
 *
 * Precedence (highest first):
 *   1. explicit frontend user preference  (localStorage "eis:theme") — set in Settings
 *   2. backend user preference            (/api/settings/user → theme)
 *   3. backend application default        (/api/settings/application → default_theme)
 *   4. "system"                           (operating-system preference)
 *
 * DOM contract: `data-theme` on <html> always holds the *effective* theme
 * ("light" or "dark") — the preference itself never lands on the element.
 * CSS keys the dark palette off `:root[data-theme="dark"]`.
 *
 * "system" cannot be persisted through the backend (which only accepts
 * light/dark), so an explicit selection lives in localStorage; the resolved
 * preference is mirrored to a separate transport cache used solely by the
 * no-flash bootstrap in index.html.
 */

import { getAppSettings, getUserPrefs } from "./settings/store.js";

export const LIGHT = "light";
export const DARK = "dark";
export const SYSTEM = "system";
export const THEMES = Object.freeze([LIGHT, DARK, SYSTEM]);
export const DEFAULT_PREFERENCE = SYSTEM;

const EXPLICIT_KEY = "eis:theme";
const RESOLVED_KEY = "eis:theme:resolved";
const OS_QUERY = "(prefers-color-scheme: dark)";

const BACKEND_THEMES = [LIGHT, DARK];

let mediaQuery = null;
let osListenerBound = false;

/* ------------------------------- pure core ------------------------------- */

/** Normalize an arbitrary value to a valid theme preference. */
export function normalizeTheme(value) {
  if (value === LIGHT || value === DARK || value === SYSTEM) return value;
  return DEFAULT_PREFERENCE;
}

/**
 * Pure resolution: the effective theme for a preference + OS state.
 * system + OS dark → dark; any explicit mode wins outright.
 * `systemIsDark` may be a boolean or the literal "dark"/"light".
 */
export function effectiveThemeFor(preference, systemIsDark) {
  const pref = normalizeTheme(preference);
  if (pref === SYSTEM) return systemIsDark === true || systemIsDark === DARK ? DARK : LIGHT;
  return pref;
}

/* -------------------------------- storage ------------------------------- */

function readStorage(key) {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function writeStorage(key, value) {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    // Storage unavailable (private mode / blocked) — theme still applies in memory.
  }
}

/* ---------------------------------- OS ---------------------------------- */

/** "dark" | "light" — conservative light fallback when matchMedia is absent. */
export function getSystemTheme() {
  const mql = getMediaQuery();
  return mql ? (mql.matches ? DARK : LIGHT) : LIGHT;
}

function getMediaQuery() {
  if (!mediaQuery && typeof window.matchMedia === "function") {
    mediaQuery = window.matchMedia(OS_QUERY);
  }
  return mediaQuery || null;
}

function ensureOsListener() {
  const mql = getMediaQuery();
  if (!mql || osListenerBound || typeof mql.addEventListener !== "function") return;
  mql.addEventListener("change", handleOsChange);
  osListenerBound = true;
}

function handleOsChange() {
  // Only system mode reacts to OS changes; explicit choices ignore them.
  if (getThemePreference() !== SYSTEM) return;
  applyTheme();
}

/* ------------------------------- preference ------------------------------ */

/**
 * Canonical preference through the precedence chain.
 * `eis:theme:resolved` is a bootstrap-only transport cache and is never
 * treated as a preference.
 */
export function getThemePreference() {
  const explicit = readStorage(EXPLICIT_KEY);
  if (THEMES.includes(explicit)) return explicit;

  const userPrefs = getUserPrefs() || {};
  if (BACKEND_THEMES.includes(userPrefs.theme)) return userPrefs.theme;

  const appSettings = getAppSettings() || {};
  if (BACKEND_THEMES.includes(appSettings.default_theme)) return appSettings.default_theme;

  return SYSTEM;
}

/** Effective theme for the current preference + OS state. */
export function getEffectiveTheme() {
  return effectiveThemeFor(getThemePreference(), getSystemTheme());
}

/* -------------------------------- application ---------------------------- */

/** Write the effective theme to the document and refresh the no-flash cache. */
export function applyTheme() {
  const preferred = getThemePreference();
  const effective = effectiveThemeFor(preferred, getSystemTheme());
  if (typeof document !== "undefined" && document.documentElement) {
    document.documentElement.dataset.theme = effective;
  }
  writeStorage(RESOLVED_KEY, preferred);
  return effective;
}

/** Persist an explicit user preference (light/dark/system) and apply it now. */
export function setThemePreference(value) {
  const pref = normalizeTheme(value);
  writeStorage(EXPLICIT_KEY, pref);
  return applyTheme();
}

/**
 * Re-evaluate the theme from the (freshly loaded or invalidated) settings
 * store without pinning an explicit local preference, then apply. Called
 * after the shell loads backend settings and after admin saves the app
 * default theme so the UI updates without a full reload.
 */
export function syncThemeFromSettings() {
  return applyTheme();
}

/** Bind the OS listener once and apply the current effective theme. */
export function initializeTheme() {
  ensureOsListener();
  return applyTheme();
}

/** Remove the OS listener — used in tests/teardown. */
export function destroyTheme() {
  if (mediaQuery && osListenerBound && typeof mediaQuery.removeEventListener === "function") {
    mediaQuery.removeEventListener("change", handleOsChange);
  }
  osListenerBound = false;
  mediaQuery = null;
}