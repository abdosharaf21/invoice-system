/**
 * Auth API endpoints — consuming the /api/auth and /api/users blueprints
 * exactly as implemented by the backend.
 */

import { api } from "../api/client.js";
import { authStore } from "./store.js";

/**
 * Login with email + password. Returns the data payload containing
 * access_token, refresh_token and user.
 */
export async function login(email, password) {
  const data = await api.post("/api/auth/login", { email, password });
  if (data.access_token) authStore.setTokens({ access: data.access_token });
  if (data.refresh_token) authStore.setTokens({ refresh: data.refresh_token });
  if (data.user) authStore.setUser(data.user);
  return data;
}

/** Fetch the current user profile via /api/auth/me. */
export async function fetchMe() {
  const data = await api.get("/api/auth/me");
  authStore.setUser(data);
  return data;
}

/**
 * Log the user out: revoke the current access token (and refresh token) on
 * the backend, then clear local state.
 */
export async function logout() {
  const { refresh } = authStore.getTokens();
  try {
    await api.post("/api/auth/logout", refresh ? { refresh_token: refresh } : {});
  } catch {
    // Even if the server call fails, the user is signed out locally.
  } finally {
    authStore.clear();
  }
}

/** Change the current user's password. */
export function changePassword(currentPassword, newPassword) {
  return api.put("/api/auth/change-password", {
    current_password: currentPassword,
    new_password: newPassword,
  });
}