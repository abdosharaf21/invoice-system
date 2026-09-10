/**
 * Auth storage and current-user state.
 *
 * Tokens live in localStorage so a refresh persists across reloads. The
 * access token has a 1-hour TTL; the refresh token a 30-day TTL — both set
 * by the backend. The user profile is cached in localStorage too so the
 * shell can render immediately, and is revalidated on startup.
 */

const ACCESS_KEY = "eis.access_token";
const REFRESH_KEY = "eis.refresh_token";
const USER_KEY = "eis.user";

let listener = null;

function read(key) {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function write(key, value) {
  try {
    if (value === null || value === undefined) window.localStorage.removeItem(key);
    else window.localStorage.setItem(key, value);
  } catch {
    /* storage may be unavailable (private mode); tokens live in memory only */
  }
}

export const authStore = {
  getTokens() {
    return {
      access: read(ACCESS_KEY),
      refresh: read(REFRESH_KEY),
    };
  },

  setTokens({ access, refresh }) {
    if (access) write(ACCESS_KEY, access);
    if (refresh) write(REFRESH_KEY, refresh);
    if (listener) listener();
  },

  getTokensSafe() {
    return this.getTokens();
  },

  getUser() {
    const raw = read(USER_KEY);
    if (!raw) return null;
    try {
      return JSON.parse(raw);
    } catch {
      return null;
    }
  },

  setUser(user) {
    if (user) write(USER_KEY, JSON.stringify(user));
    else write(USER_KEY, null);
    if (listener) listener();
  },

  clear() {
    write(ACCESS_KEY, null);
    write(REFRESH_KEY, null);
    write(USER_KEY, null);
    if (listener) listener();
  },

  isAuthenticated() {
    return Boolean(this.getTokens().access);
  },

  onChange(fn) {
    listener = fn;
  },
};

export function getCurrentRole() {
  const user = authStore.getUser();
  if (!user || !Array.isArray(user.roles) || user.roles.length === 0) return null;
  return user.roles[0];
}

export function hasRole(...allowed) {
  const role = getCurrentRole();
  return allowed.includes(role);
}

/** Roles allowed to use imports, reconciliation and reports. */
export function canReconcile() {
  return hasRole("admin", "accountant", "manager");
}

/** Roles allowed to administer users. */
export function isAdmin() {
  return hasRole("admin");
}