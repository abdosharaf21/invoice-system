/**
 * Frontend configuration.
 *
 * API_BASE points at the Flask backend. The backend already allows the
 * ``http://localhost:3000`` / ``http://localhost:5173`` and the static
 * ``http://localhost:8899`` / ``http://127.0.0.1:8899`` (and their
 * ``http://0.0.0.0:*`` loopback siblings) origins via CORS.
 * Override the base URL at runtime with ``?api=http://host:port`` or
 * ``window.__EIS_API_BASE__`` if the backend is served elsewhere.
 *
 * When the SPA is served from a non-localhost host (production), the API
 * defaults to the same origin via ``/api`` — e.g. an Nginx server block that
 * proxies ``/api`` to Gunicorn. No source edit is required.
 */

const DEFAULT_API_BASE = "http://localhost:5001";

function isLocalHost() {
  const host = window.location.hostname;
  // ``0.0.0.0`` is the loopback the local static server is often bound to
  // (``python3 -m http.server 8899``); browsers present it verbatim, so it
  // must resolve to the local backend just like localhost / 127.0.0.1.
  return host === "localhost" || host === "127.0.0.1" || host === "::1" || host === "0.0.0.0";
}

function resolveApiBase() {
  const fromQuery = new URLSearchParams(window.location.search).get("api");
  if (fromQuery) return fromQuery.replace(/\/+$/, "");
  if (window.__EIS_API_BASE__) {
    return String(window.__EIS_API_BASE__).replace(/\/+$/, "");
  }
  if (!isLocalHost()) {
    return "/api";
  }
  return DEFAULT_API_BASE;
}

export const CONFIG = Object.freeze({
  apiBase: resolveApiBase(),
});

export const LIMITS = Object.freeze({
  maxUploadBytes: 10 * 1024 * 1024, // matches backend MAX_CONTENT_LENGTH
  maxPageSize: 200,
  defaultPageSize: 50,
});

export const ACCEPTED_UPLOAD_EXTENSIONS = [".csv", ".xlsx"];