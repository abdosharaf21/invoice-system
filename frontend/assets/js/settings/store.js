/**
 * Settings store — caches application + company settings for the shell and
 * page renderers. Values always come from the backend (so edits persist),
 * fetched once per page navigation session and refreshed on demand.
 */

import { getApplicationSettings, getCompanySettings, getUserSettings } from "../services/settings.js";

let appCache = null;
let companyCache = null;
let userCache = null;
let appLoading = null;
let companyLoading = null;
let userLoading = null;

export function getAppSettings() {
  return appCache || {};
}

export function getCompanyInfo() {
  return companyCache || {};
}

export function getAppName() {
  return (appCache && appCache.application_name) || "E-Invoice & Reconciliation";
}

export function getAppSubtitle() {
  return (appCache && appCache.application_subtitle) || "Tax authority compliance";
}

export function getCompanyName() {
  return (companyCache && companyCache.name) || null;
}

/** Fetch (once) and cache application settings. Returns current cache. */
export async function loadAppSettings(force = false) {
  if (appCache && !force) return appCache;
  if (appLoading && !force) return appLoading;
  appLoading = (async () => {
    try {
      appCache = await getApplicationSettings();
    } catch {
      // Keep the previous snapshot; unknown names fall back to defaults.
    }
    return appCache;
  })();
  return appLoading;
}

/** Fetch (once) and cache the current company. Returns current cache. */
export async function loadCompanySettings(force = false) {
  if (companyCache && !force) return companyCache;
  if (companyLoading && !force) return companyLoading;
  companyLoading = (async () => {
    try {
      companyCache = await getCompanySettings();
    } catch {
      // Keep the previous snapshot.
    }
    return companyCache;
  })();
  return companyLoading;
}

/** The current user's own preferences (their theme/language/formatting). */
export function getUserPrefs() {
  return userCache || {};
}

/** Fetch (once) and cache the current user's preferences. */
export async function loadUserPrefs(force = false) {
  if (userCache && !force) return userCache;
  if (userLoading && !force) return userLoading;
  userLoading = (async () => {
    try {
      userCache = await getUserSettings();
    } catch {
      // Keep the previous snapshot.
    }
    return userCache;
  })();
  return userLoading;
}

export function invalidateSettings() {
  appCache = null;
  companyCache = null;
  userCache = null;
  appLoading = null;
  companyLoading = null;
  userLoading = null;
}