/**
 * Settings API client — consuming /api/settings (application, company, user).
 *
 * The backend wraps every response as { success, data, message } and the
 * shared api client unwraps `data`, so these functions return the payload
 * object directly.
 */

import { api } from "../api/client.js";

/** Application settings safe subset (any authenticated user). */
export async function getApplicationSettings() {
  return api.get("/api/settings/application");
}

/** Update application settings (admin only). */
export async function updateApplicationSettings(payload) {
  return api.put("/api/settings/application", payload);
}

/** The current user's organisation profile (any authenticated user). */
export async function getCompanySettings() {
  return api.get("/api/settings/company");
}

/** Update the current user's organisation profile (admin only). */
export async function updateCompanySettings(payload) {
  return api.put("/api/settings/company", payload);
}

/** The authenticated user's own preferences. */
export async function getUserSettings() {
  return api.get("/api/settings/user");
}

/** Update the authenticated user's own preferences only. */
export async function updateUserSettings(payload) {
  return api.put("/api/settings/user", payload);
}