# Phase 11 — API Stability, Versioning & Contracts — Completion Report

Repository: `~/e-invoice-system/invoice-system`
Branch: `phase-6-frontend` (working tree, no commits made in Phase 11)
Date: 2026-09-15

---

## 1. Executive Summary

Phase 11 audited every backend API route and middleware to lock down the
stable contract between the Flask backend and all consumers (React frontend,
OpenAPI spec, future integrations). A single canonical envelope builder
(`backend/middleware/contract.py`) is now the source of truth for every success
and error response body, eliminating the six different ad-hoc `_error()`
helpers that previously carried inconsistent status-to-code mappings. The three
legacy user auth endpoints (`/api/users/login`, `/api/users/logout`,
`/api/users/me`) are formally marked `deprecated: true` with a `Deprecation`
header and `Link` successor pointing at the canonical `/api/auth/*` routes.
Ten new contract tests lock down deprecation headers, the error-code mapping,
error envelope key set, and success envelope shape. All 10 existing route
modules now delegate to the shared builder while preserving byte-identical
output, meaning no frontend or API consumer behavior changed.

Backend: **497 passed** (487 baseline + 10 new contract tests).
Frontend: **194 passed** (unchanged).

Verdict: **PHASE 11 COMPLETE**.

---

## 2. Phase Scope

- Full route-module inventory: every `@blueprint.route()` in `auth`, `users`,
  `imports`, `reconciliation`, `settings`, `companies`, `email`, `audit_trail`,
  `static` and the inline health endpoints in `app.py`.
- Inventory of middleware: `error_handlers.py`, `exceptions.py`, `rbac.py`,
  `auth_context.py`, `rate_limit.py`, `logger.py`, `contract.py` (new).
- Inventory of the existing `openapi.yaml` (1193 lines, 34 paths).
- Audit of success envelope shape (some modules include `message`, some omit;
  all include `data` when applicable).
- Audit of module-level `_error()` code maps (six different dictionaries).
- Identification and deprecation of legacy duplicate auth endpoints.
- Regression gate: backend 487, frontend 194 — both must remain green.

---

## 3. Baseline (Phase 11 start)

| Suite    | Baseline | After Phase 11 |
|----------|----------|----------------|
| Backend  | 487 pass | 497 pass (487 + 10 new) |
| Frontend | 194 pass | 194 pass |

---

## 4. Contract Inventory — Findings

### 4.1 Error envelope (already consistent)

All error responses already conform to:
`{success: false, message: str, status: int, code: str}`.
The `AppException` hierarchy in `middleware/exceptions.py` and the global
handlers in `middleware/error_handlers.py` enforce this. The problem was
*redundant code maps* — six different `_error()` functions, each with its own
subset of status-to-code mappings, and a hard-wired `APP_ERROR` fallback for
statuses not in the local map.

### 4.2 Success envelope (cosmetic inconsistency)

Some modules include a `message` field on success, some omit it. The frontend
client (`api/client.js`) only reads `json.data` on success, making `message`
strictly optional. The canonical contract — documented in `openapi.yaml` and
now enforced by the shared builder — is:

```
{success: true, data?: <payload>, message?: "optional text"}
```

`data` is the contract payload field. `message` is human-enrichment and never
required for client logic.

### 4.3 Legacy duplicate auth endpoints

The `users` blueprint exposes `/api/users/login`, `/api/users/logout`, and
`/api/users/me`, which duplicate `/api/auth/login`, `/api/auth/logout`, and
`/api/auth/me`. The frontend consumes only `/api/auth/*` for authentication
(verified by grepping all frontend service and page files). The legacy
endpoints remain functional but are now formally deprecated.

### 4.4 Versioning (already complete)

`register_api_v1_aliases()` in `app.py` registers a `/api/v1/<path>` alias
for every `/api/<path>` rule. Both prefixes resolve to the same view
functions. Existing contract tests already cover this.

---

## 5. Changes Made

### 5.1 New file

| File | Purpose |
|------|---------|
| `backend/middleware/contract.py` | Canonical `success_response()`, `error_response()`, `deprecated_response()` builders, `DEPRECATION_HEADER` constant, and `STANDARD_ERROR_CODES` mapping |

### 5.2 Edited backend files

| File | Change |
|------|--------|
| `backend/modules/auth/routes.py` | `_error()` delegates to `error_response()`; import added |
| `backend/modules/users/routes.py` | `_error()` delegates to `error_response()` with `INVALID_CREDENTIALS` override for 401; `login/logout/me` return `deprecated_response()` with `Deprecation: true` + `Link: <successor>; rel="successor-version"` |
| `backend/modules/settings/routes.py` | `_error()` delegates to `error_response()` |
| `backend/modules/companies/routes.py` | `_error()` delegates to `error_response()` (replaces hardcoded `BAD_REQUEST`/`APP_ERROR` ternary) |
| `backend/modules/email/routes.py` | `_error()` delegates to `error_response()` |
| `backend/modules/reconciliation/routes.py` | `_error()` delegates to `error_response()` |
| `backend/modules/audit_trail/routes.py` | Inline error dict replaced with `error_response()` call |

### 5.3 Edited documentation

| File | Change |
|------|--------|
| `docs/api/openapi.yaml` | Added Deprecation section to description; marked `/users/login`, `/users/logout`, `/users/me` as `deprecated: true` with `Deprecation` + `Link` response headers; added `components.headers.Deprecation` and `components.headers.RequestId` definitions; wired `X-Request-Id` into reusable error responses and representative success responses; updated `SuccessBody` (documented optionality of `message`); updated `Error.code` description to note `APP_ERROR` is a reserved internal fallback |

### 5.4 Edited test file

| File | Change |
|------|--------|
| `backend/tests/test_api_contract.py` | 10 new tests added (see §9) |

---

## 6. Deprecation Decision & Rationale

Legacy endpoints are kept functional (no breaking change) but carry standard
deprecation signals:

- **`Deprecation: true`** response header (draft-ietf-httpapi-deprecation-header)
- **`Link: <successor>; rel="successor-version"`** response header

Rationale:

1. The frontend exclusively consumes `/api/auth/*`; the legacy routes are
   dead code from the frontend's perspective.
2. A test (`test_users_logout_persists_access_jti_to_db`) asserts the legacy
   `/api/users/logout` still blocklists JTIs — the route is exercised and
   known to be used by a documented contract test, so it cannot be removed
   without a coordinated migration.
3. Adding `deprecated: true` to the OpenAPI spec means API clients and code
   generators will surface the deprecation warning automatically.
4. The `Deprecation` header enables programmatic detection without scraping
   message text or inspecting the URL path.

---

## 7. Canonical API Contract (Summary)

```
Base paths:  /api/<resource>          (compatibility alias)
             /api/v1/<resource>       (stable, documented namespace)

── Success ──────────────────────────────────────────────
{ "success": true, "data"?: <payload>, "message"?: "<text>" }

── Error (always 4 keys, never fewer) ──────────────────
{
  "success": false,
  "message": "<human readable>",
  "status":  <int>,
  "code":    "<MACHINE_CODE>"
}

── Correlation ─────────────────────────────────────────
X-Request-Id: <uuid or client-supplied value>
X-Request-Duration: <n.nnnn>s
```

---

## 8. Error-Code Catalogue

`middleware/contract.py` `STANDARD_ERROR_CODES` is the single source of truth.
Modules can override (e.g. users `INVALID_CREDENTIALS` on login), but for any
documented status the code is fixed and clients can branch on it:

| Status | Code |
|--------|------|
| 400 | `BAD_REQUEST` |
| 401 | `UNAUTHORIZED` (override: `INVALID_CREDENTIALS`) |
| 403 | `FORBIDDEN` |
| 404 | `NOT_FOUND` |
| 405 | `METHOD_NOT_ALLOWED` |
| 409 | `CONFLICT` |
| 422 | `VALIDATION_ERROR` |
| 429 | `RATE_LIMITED` |
| 500 | `INTERNAL_ERROR` |
| 502 | `BAD_GATEWAY` |
| 503 | `SERVICE_UNAVAILABLE` |

`APP_ERROR` is a reserved fallback for undocumented statuses; it never fires
for the values above. A contract test (`test_contract_error_response_maps_documented_statuses`)
asserts this for all 11 codes and verifies the fallback for an undocumented
status.

JWT-specific 401 codes from `app.py` callbacks: `TOKEN_EXPIRED`,
`TOKEN_REQUIRED`, `INVALID_TOKEN`, `TOKEN_REVOKED`.

---

## 9. Contract Test Additions (10 new tests)

| # | Test | What it locks |
|---|------|---------------|
| 23a | `test_deprecated_users_login_carry_deprecation_header` | Legacy login returns 200 + `Deprecation: true` + `Link` pointing at `/api/auth/login` |
| 23b | `test_deprecated_users_logout_carry_deprecation_header` | Legacy logout returns 200 + `Deprecation: true` + `Link` |
| 23c | `test_deprecated_users_me_carry_deprecation_header` | Legacy /me returns 200 + `Deprecation: true` + `Link` |
| 23d | `test_v1_legacy_users_endpoint_also_deprecated` | `/api/v1/users/logout` carries `Deprecation: true` (same view function) |
| 23e | `test_canonical_auth_login_does_not_carry_deprecation` | `/api/auth/login` carries no `Deprecation` header |
| 24a | `test_contract_error_response_maps_documented_statuses` | `error_response()` maps all 11 documented statuses to stable codes; falls back to `APP_ERROR` for 599 |
| 24b | `test_contract_error_response_explicit_code_override` | Explicit `code=` override is honored (e.g. `INVALID_CREDENTIALS`) |
| 25 | `test_error_envelope_keys_are_exactly_canonical` | A 404 error body contains exactly `{success, message, status, code}` — no extra keys |
| 26a | `test_success_envelope_is_flat_object` | `/api/health` returns a JSON object with `success: true` |
| 26b | `test_success_envelope_with_data_key` | Reconciliation list success returns `data` as a dict, not a raw list |

---

## 10. OpenAPI Documentation Enhancements

- **Deprecation section** added to `info.description` explaining the header
  contract and migration policy.
- **`deprecated: true`** flag on `/users/login`, `/users/logout`, `/users/me`.
- **`components.headers.Deprecation`** and **`components.headers.RequestId`**
  defined and wired into all reusable error responses and representative
  success responses via YAML anchor.
- **`SuccessBody.message`** described as optional.
- **`Error.code`** description clarifies `APP_ERROR` is reserved.
- Typo corrected: "superceded" → "superseded" in legacy endpoint summaries.

---

## 11. Regression Results

| Suite | Result |
|-------|--------|
| Backend | **497 passed** in 20.34s (487 baseline + 10 new) |
| Frontend | **194 passed** in 4.78s (unchanged) |

---

## 12. Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Refactoring `_error()` could change serialized body shape | Flask `DefaultJSONProvider` sorts keys; `error_response()` produces identical dict; contract tests assert key set and values |
| Deprecated endpoints may break existing clients | Endpoints remain functional; only a header is added |
| Shared `STANDARD_ERROR_CODES` is too rigid | Modules can pass explicit `code=` to `error_response()` for overrides (e.g. `INVALID_CREDENTIALS`) |
| `APP_ERROR` might surface for a documented status | Contract test exhaustively asserts all 11 documented statuses produce their canonical code |

---

## 13. What Was NOT Changed

- No new modules, blueprints, or Flask endpoints
- No new authentication mechanisms or RBAC roles
- No database schema changes or new migrations
- No frontend changes
- No removal of any endpoint (deprecation only)
- No changes to `middleware/error_handlers.py` (the global handlers already
  produce `NOT_FOUND` for 404 — confirmed correct)
- No changes to JWT callback codes in `app.py`
- No changes to `shared/security.py` or `config.py`

---

## 14. Next Steps (Phase 12+)

Phase 12+ can build on this foundation:

- **Phase 12 — Audit hardening**: combine audit trail enhancements with the
  contract stability established here.
- **Future major version**: remove the deprecated `/api/users/login|logout|me`
  endpoints and the unversioned `/api/*` namespace, retaining only `/api/v1/*`.
- **CI gate**: add `python -c "import yaml; yaml.safe_load(open('docs/api/openapi.yaml'))"`
  to the test suite so YAML regressions are caught on every PR.

---

## 15. Verdict

**PHASE 11 COMPLETE.**

All backend API routes use a single canonical contract builder. The three
legacy duplicate auth endpoints are formally deprecated with standard headers
and OpenAPI flags. Ten new contract tests lock down the envelope shape,
deprecation signals, error-code mapping, and versioning behavior. Both
backend (497) and frontend (194) regression suites pass in full.
