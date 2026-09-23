/**
 * Centralized API client.
 *
 * Responsibilities:
 *  - attach the access token to every request
 *  - transparently refresh an expired access token and retry the request
 *  - redirect to login on unrecoverable authentication failure
 *  - normalize backend JSON envelopes and errors into a consistent promise
 *  - expose helpers for file uploads and file downloads
 *
 * The backend error envelope is:
 *   { success: false, message, status, code, errors? }
 * Success envelopes are:
 *   { success: true, data, ... }
 */

import { CONFIG } from "../config.js";
import { authStore } from "../auth/store.js";

// Circular-safe dependency: normalising module to avoid a hard cycle.
let onAuthFailure = null;

export function setAuthFailureHandler(fn) {
  onAuthFailure = fn;
}

function readTokenPair() {
  return authStore.getTokens();
}

function writeTokens(access, refresh) {
  authStore.setTokens({ access, refresh });
}

export class ApiError extends Error {
  constructor(message, { status = 0, code = "UNKNOWN", errors = null, details = null } = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.errors = errors;
    this.details = details;
  }
}

async function parseBody(res) {
  const ct = (res.headers.get("content-type") || "").toLowerCase();
  if (ct.includes("application/json")) {
    try {
      return { json: await res.json() };
    } catch {
      return { json: null };
    }
  }
  return { json: null };
}

function readRequestId(res) {
  return res.headers.get("x-request-id") || null;
}

function toApiError(res, json, requestId = null) {
  if (json && json.message) {
    return new ApiError(json.message, {
      status: res.status,
      code: json.code,
      errors: json.errors,
      details: requestId ? { request_id: requestId } : null,
    });
  }
  return new ApiError(`Request failed with status ${res.status}`, {
    status: res.status,
    details: requestId ? { request_id: requestId } : null,
  });
}

/**
 * Join the configured API base with an endpoint path.
 *
 * - base is either an origin ("http://localhost:5001") or a same-origin
 *   mount ("/api") when the SPA is served on a non-localhost host.
 * - paths passed by callers are full backend paths ("/api/auth/login"), so
 *   a base that already ends with "/api" must not be prefixed twice —
 *   otherwise the request leaves as "/api/api/auth/login" and every API call
 *   breaks against the static origin.
 */
export function joinApiBase(base, path) {
  const b = String(base ?? "").replace(/\/+$/, "");
  if (!b) return path;
  if (b === "/api" && (path === "/api" || path.startsWith("/api/"))) {
    return path;
  }
  return `${b}/${String(path).replace(/^\/+/, "")}`;
}

function apiUrl(path) {
  return path.startsWith("http") ? path : joinApiBase(CONFIG.apiBase, path);
}

async function request(path, { method = "GET", body, headers = {}, isForm = false } = {}) {
  const { access } = readTokenPair() || {};
  const url = apiUrl(path);

  const init = {
    method,
    headers: { ...headers },
  };

  if (access) init.headers.Authorization = `Bearer ${access}`;

  if (body !== undefined) {
    if (isForm) {
      init.body = body; // FormData — let the browser set the multipart boundary
    } else {
      init.headers["Content-Type"] = "application/json";
      init.body = JSON.stringify(body);
    }
  }

  let res = await fetch(url, init);

  // Single seamless retry on an expired access token.
  let refreshed = false;
  if (res.status === 401 && access) {
    const ok = await refreshTokens();
    if (ok) {
      refreshed = true;
      const { access: newAccess } = readTokenPair() || {};
      init.headers.Authorization = `Bearer ${newAccess}`;
      if (!isForm && body !== undefined) {
        // Rebuild the JSON body (must be an object for reserialization).
        init.body = JSON.stringify(body);
      }
      res = await fetch(url, init);
    }
  }

  const { json } = await parseBody(res);

  if (!res.ok) {
    if (res.status === 401) {
      // Either a purely non-JSON auth failure, or a 401 that survived a
      // successful refresh — both mean the session cannot continue.
      if ((!json || refreshed) && onAuthFailure) await onAuthFailure();
    }
    throw toApiError(res, json, readRequestId(res));
  }

  return { res, json };
}

async function refreshTokens() {
  const { access, refresh } = readTokenPair() || {};
  if (!refresh) return false;

  try {
    const res = await fetch(apiUrl("/api/auth/refresh"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refresh }),
    });
    const { json } = await parseBody(res);
    if (res.ok && json && json.data && json.data.access_token) {
      writeTokens(json.data.access_token, refresh);
      return true;
    }
    if (onAuthFailure) await onAuthFailure();
    return false;
  } catch {
    if (onAuthFailure) await onAuthFailure();
    return false;
  }
}

/**
 * JSON request helper. Returns the unwrapped `data` payload.
 * Usage: api.get("/api/foo"), api.post("/api/foo", {…}), …
 */
export const api = {
  async get(path, params) {
    const { res, json } = await request(buildPath(path, params), { method: "GET" });
    return (json && json.data) || (res.status === 200 ? {} : null);
  },

  async post(path, body) {
    const { json } = await request(path, { method: "POST", body });
    return (json && json.data) || {};
  },

  async put(path, body) {
    const { json } = await request(path, { method: "PUT", body });
    return (json && json.data) || {};
  },

  async del(path) {
    const { json } = await request(path, { method: "DELETE" });
    return (json && json.data) || {};
  },

  /** Multipart upload. Accepts a FormData object. Returns unwrapped data. */
  async upload(path, formData) {
    const { json } = await request(path, { method: "POST", body: formData, isForm: true });
    return (json && json.data) || {};
  },

  /**
   * Trigger a file download from a backend export endpoint. Returns the
   * filename the server suggested (for display) — the file is saved from
   * the Blob including our auth token (a plain <a href> cannot send the
   * Authorization header).
   */
  async download(path, params) {
    const url = buildPath(path, params);
    const { access } = readTokenPair() || {};
    let res = await fetch(apiUrl(url), {
      method: "GET",
      headers: access ? { Authorization: `Bearer ${access}` } : {},
    });

    // Seamless refresh + retry for an expired access token, mirroring
    // `request`: silently retry once, then hand the session to the app.
    let refreshed = false;
    if (res.status === 401 && access) {
      const ok = await refreshTokens();
      if (ok) {
        refreshed = true;
        const { access: newAccess } = readTokenPair() || {};
        res = await fetch(apiUrl(url), {
          method: "GET",
          headers: newAccess ? { Authorization: `Bearer ${newAccess}` } : {},
        });
      }
    }

    if (!res.ok) {
      const { json } = await parseBody(res);
      // A 401 that survived a successful refresh (or a non-JSON 401) means
      // the session cannot continue. Refresh-failure already handled inside
      // refreshTokens() — don't fire the handler a second time.
      if (res.status === 401 && (!json || refreshed) && onAuthFailure) {
        await onAuthFailure();
      }
      const message = json && json.message ? json.message : `Export failed with status ${res.status}`;
      const requestId = readRequestId(res);
      throw new ApiError(message, {
        status: res.status,
        code: json && json.code,
        details: requestId ? { request_id: requestId } : null,
      });
    }

    const blob = await res.blob();

    const cd = res.headers.get("content-disposition") || "";
    const m = /filename="([^"]+)"/.exec(cd);
    let filename = m ? m[1] : "export";
    // The server sets download_name without the attachment label in some cases.
    if (!/\.(csv|xlsx)$/i.test(filename)) filename += guessExt(path);

    const objectUrl = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = objectUrl;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(() => URL.revokeObjectURL(objectUrl), 4000);
    return filename;
  },
};

function guessExt(path) {
  if (path.includes("/results/export") || path.includes("/errors/export")) {
    return path.split("?").find((p) => p.startsWith("format="))
      ? `/${path.split("format=")[1].split("&")[0]}`
      : ".csv";
  }
  return ".csv";
}

function buildPath(path, params) {
  if (!params) return path;
  const search = new URLSearchParams();
  let order = 0;
  for (const [key, raw] of Object.entries(params)) {
    if (raw === undefined || raw === null || raw === "") continue;
    order += 1;
    // Preserve explicit insertion order for tests/deterministic query strings.
    search.set(key, String(raw));
  }
  if (!order) return path;
  return `${path}?${search.toString()}`;
}

/** Normalized access to the request internals (used by tests). */
export function _internal() {
  return { request, buildPath, refreshTokens, joinApiBase };
}