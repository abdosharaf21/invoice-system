/**
 * Frontend configuration.
 *
 * API_BASE points at the Flask backend. The backend already allows the
 * ``http://localhost:3000`` / ``http://localhost:5173`` origins via CORS.
 * Override the base URL at runtime with ``?api=http://host:port`` or
 * ``window.__EIS_API_BASE__`` if the backend is served elsewhere.
 */

const DEFAULT_API_BASE = "http://localhost:5001";

function resolveApiBase() {
  const fromQuery = new URLSearchParams(window.location.search).get("api");
  if (fromQuery) return fromQuery.replace(/\/+$/, "");
  if (window.__EIS_API_BASE__) {
    return String(window.__EIS_API_BASE__).replace(/\/+$/, "");
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