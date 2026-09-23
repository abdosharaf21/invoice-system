# Phase 20 Report — Settings Restructuring (Information Architecture)

**Status: COMPLETE · verdict-grade: all sections classified · repository:** `~/e-invoice-system/invoice-system`
**Date:** 2026-09-19
**Validation class: DETERMINISTIC** — every change is exercised by the automated
frontend suite (node:test) and the backend regression suite (pytest), reused to
gate the pre-existing baseline (210 frontend / 706 backend).

| Verdict | Meaning |
|---|---|
| **PASS** | Implemented and verified by the automated suites (and/or direct code/contract inspection). |
| **PASS (drill)** | Behavior demonstrated through an isolated/exercised path (test harness, throwaway data). |
| **FAIL / DEFECT** | A defect found during validation, recorded with evidence. |
| **BACKEND CAPABILITY REQUIRED** | The UI/UX requirement cannot be honestly met on the current API contract — requires a backend (or infra) capability this phase did not introduce; gated, never faked with mock UI. |
| **DEFERRED** | Real change, intentionally sequenced out of this phase (documented). |
| **N/A (environment)** | Requires a live service/host/browser that does not exist here. |

---

## 1. Objective

Reorganise the Settings information architecture into eight clear sections —
**General / Application, Organization, My Profile, Security, Email & Notifications,
Appearance, Language & Regional, System** — while preserving the route-driven
`#/settings/:section` navigation, sidebar and breadcrumb integration completed
in Phase 19. Language controls belong in **Language & Regional**; theme controls
belong in **Appearance**; Security hosts only genuinely-supported controls;
no fake or decorative controls are introduced. This phase changes **no backend
API contracts or database schema** and re-homes existing working controls rather
than removing functionality.

## 2. Baseline (pre-change state)

| Check | Result |
|---|---|
| Backend suite | `706 passed / 11 skipped` (`.venv/bin/python -m pytest -q`, ~45 s) |
| Frontend suite | `210 passed / 0 failed` (`cd frontend && npm test`) |
| General | Held `application_name`, `application_subtitle`, **`default_language`**, **`default_theme`**, date/number/timezone defaults, page-size default |
| `#default-language-hint` | Wired inside **General** (aria-describedby on `default_language`) |
| Security section | Placeholder ("No settings are available in this section yet") |
| My Profile | Signed-in identity + personal `pagination_size` (only backend-supported personal control) |
| System section | Placeholder (reserved, no supported controls) |

## 3. Audit findings (read-only audit, executed before implementation)

**Current → target section mapping**

| Target | Current section | Content at audit | Action |
|---|---|---|---|
| **General / Application** | `general` (admin) | name, subtitle, `default_language`, `default_theme`, date/number/timezone defaults, default page size | Drop `default_language` + `default_theme` (→ their content sections); relabel format/timezone defaults as "Default …" |
| **Organization** | `organization` (admin) | 9 company/tax/contact fields | Unchanged |
| **My Profile** | `profile` (all) | signed-in identity + `pagination_size` | Unchanged |
| **Security** | `security` (all) | placeholder | Implement real change-password (`PUT /api/auth/change-password` exists and is backend-tested) |
| **Email & Notifications** | `email` (admin) | SMTP status, workflows, test form | Unchanged |
| **Appearance** | `appearance` (all) | personal theme | Add admin-only **Application default theme** sub-card |
| **Language & Regional** | `regional` (all) | personal language/date/number/timezone | Add admin-only **Application default language** sub-card + relocated hint |
| **System** | `system` (all) | placeholder | Unchanged — **DEFERRED** |

**Controls that moved**
- `default_language` (application default for new accounts) — General → Language & Regional (admin-only "Application defaults" sub-card). Explicit requirement #6.
- `default_theme` (application-wide shell default) — General → Appearance (admin-only sub-card). Explicit requirement #7 ("Appearance/theme controls belong in **Appearance**").

**Controls removed** — none. Both moved controls remain live and backed by the
same admin PUT on `/api/settings/application`; nothing is dropped or faked.

**Controls requiring backend capability**
- Notification-preference toggles (per-workflow enable/disable) — backend exposes
  read-only email status only → **BACKEND CAPABILITY REQUIRED** (unchanged from Phase 19 Req #3).
- SMTP server configuration UI — **BACKEND CAPABILITY REQUIRED** (unchanged).
- System section content — no safe frontend subset is exposed → **DEFERRED**.

**Controls that remain unchanged**
- Organization (all 9 fields), My Profile (`pagination_size`), Email status + test form, personal theme, personal language/date/number/timezone.

**Risks / ambiguities surfaced (and how resolved)**
1. The `#default-language-hint` aria-describedby wiring lived in General — relocated with the control to Language & Regional; the Arabic-save regression test was updated accordingly.
2. The General PUT payload must stop owning `default_language`/`default_theme` — `readAppForm` updated.
3. The Account page's "password expires every 90 days …" copy is **not backed by any server policy** (audited: no expiry/reuse enforcement exists) — the new Security section deliberately renders only the password form with no unsupported policy claims.
4. Sub-cards are strictly admin-gated so non-admins never see admin-only controls (no disabled/fake admin UI).

## 4. Final Settings structure

| Section | Route | Access | Controls (all backend-backed) |
|---|---|---|---|
| **General / Application** | `#/settings/general` | admin | Application name, Subtitle; Default date format, Default number format, Default timezone; Default page size |
| **Organization** | `#/settings/organization` | admin | Company name, Tax registration number, Billing email, Phone, Address, Website, Default currency, Default tax rate, Fiscal year start |
| **My Profile** | `#/settings/profile` | all | Signed-in identity banner; Page size |
| **Security** | `#/settings/security` | all | Change password (current / new / confirm) → `PUT /api/auth/change-password` |
| **Email & Notifications** | `#/settings/email` | admin | SMTP status + connection details, automatic-notification workflow list, test-email form |
| **Appearance** | `#/settings/appearance` | all | Personal theme (light / dark / system) + ▸ *Application defaults*: Default theme (admin) |
| **Language & Regional** | `#/settings/regional` | all | Personal language / date format / number format / timezone + ▸ *Application defaults*: Default language + hint (admin) |
| **System** | `#/settings/system` | all | Placeholder (reserved; no supported controls — DEFERRED) |

Every section remains a real routable sub-route; the sidebar (`#/settings`),
internal nav (`#/settings/:id` anchors with `data-section` + `aria-current`),
and breadcrumbs (`Administration / Settings / <section>`) are untouched.

## 5. Files changed

| File | Change |
|---|---|
| `frontend/assets/js/pages/settings.js` | Re-homed `default_language`/`default_theme`; new admin-only "Application defaults" sub-card helper; new Security change-password section; General form/`readAppForm` scoped to identity + non-personal defaults; header doc updated |
| `frontend/assets/js/i18n/en.js` | Added `settings.appDefaultsTitle`, `settings.labelDefaultDateFormat`, `settings.labelDefaultNumberFormat`, `settings.labelDefaultTimezone`; reworded `settings.defaultLanguageHint` |
| `frontend/assets/js/i18n/ar.js` | Same keys/strings in Arabic (parity preserved) |
| `frontend/test/settings.test.js` | Arabic-save hint assertion moved General → Regional; `beforeEach` resets locale to `en`; +4 new tests (default re-homing, non-admin gating, Security change-password, My Profile scope) |
| `PHASE20_REPORT.md` | This report |

## 6. Backend capabilities used

All controls map 1:1 to existing, backend-tested endpoints — no new frontend API
surface, no contract changes:

| Control | Endpoint(s) |
|---|---|
| General identity + defaults | `GET/PUT /api/settings/application` (PUT admin-gated) |
| Organization 9 fields | `GET/PUT /api/settings/company` (PUT admin-gated) |
| My Profile page size | `GET/PUT /api/settings/user` (self) |
| Security change password | `PUT /api/auth/change-password` (self; backend-tested in `test_auth_http_gaps.py`) |
| Email status + test | `GET /api/email/status`, `POST /api/email/test` |
| Appearance personal theme / app default theme | `GET/PUT /api/settings/user`; `GET/PUT /api/settings/application` |
| Language & Regional personal / app default language | `GET/PUT /api/settings/user`; `GET/PUT /api/settings/application` |

## 7. Deferred / backend-required items

- **Notification-preference toggles** — **BACKEND CAPABILITY REQUIRED** (read-only email status only).
- **SMTP server configuration UI** — **BACKEND CAPABILITY REQUIRED**.
- **System section content** — **DEFERRED** (no supported settings surfaced; stays a clearly-marked reserved placeholder).
- **Remember Me / Forgot Password** — **DEFERRED** (unchanged from Phase 19; no persistent-login / reset endpoints).
- **Password expiry/reuse policy copy** — NOT SHOWN (no server policy exists; omitted rather than faked).
- **My Profile identity editing / avatar upload** — NOT ADDED (`/api/settings/user` update supports only `language, theme, date_format, number_format, timezone, pagination_size`; `avatar_path` is returned but non-writable).

## 8. Tests (before / after)

| Suite | Before | After | Delta |
|---|---|---|---|
| Frontend (`cd frontend && npm test`) | 210 passed / 0 failed | **214 passed / 0 failed** | +4 tests |
| Backend (`../.venv/bin/python -m pytest -q`) | 706 / 11 | **706 passed / 11 skipped** | 0 (backend untouched) |

New/updated frontend coverage:
- **homes language and theme defaults in their content sections, not General** — asserts no `default_language`/`default_theme` in General; `default_language` + `#default-language-hint` + aria-describedby present in Language & Regional; `default_theme` in Appearance.
- **keeps the Application-defaults blocks hidden for non-admins** — viewer sees no admin sub-cards while personal controls still render.
- **Security renders a real change-password form backed by the backend** — fields render; submit issues `PUT /api/auth/change-password` with exactly `{current_password, new_password}`; success state announced.
- **My Profile exposes only backend-supported personal controls** — `pagination_size` present; no `full_name`/`email`/`avatar_path` editors.
- Arabic-save regression updated: the `#default-language-hint`/aria-describedby assertion now targets Language & Regional (where the control lives) instead of General.
- The rendering-suite `beforeEach` now resets the locale to `en` after an earlier test persists Arabic — keeps every subsequent test on an English/LTR baseline.

## 9. EN/AR validation

- `i18n.test.js` **dictionary parity** is green: every key in `ar.js` mirrors `en.js` exactly and resolves to a non-empty string; all 4 new keys added in both locales.
- Arabic save flow re-verified by the regression test: re-render in `ar`, Arabic section nav (`اللغة والإقليم`), Arabic toast (`تم حفظ التفضيلات الشخصية`), `<html lang="ar" dir="rtl">`.

## 10. RTL / LTR validation

- **No CSS was changed** in this phase; all new UI reuses existing logical-property
  form/card/nav classes (`settings-layout`, `form-grid`, `.field label`, `.card`),
  so nothing introduces physical left/right assumptions.
- The `rtl-guard` suite (no physical `margin-left/right`/`padding-left/right` in
  assets CSS/JS) is green as part of the 214.
- Document direction flip on language save is exercised by the existing English/Arabic save tests (`dir=rtl` assert).
- Split-pane ordering, input icons, password toggles and buttons are unaffected
  (no Login-page changes in this phase).

## 11. Responsive / accessibility validation

- **Responsive:** unchanged `.settings-layout → 1fr` below 860 px; nav wraps to a
  horizontal row; new sub-cards share the same card/grid behaviour.
- **Labels/focus/keyboard:** every field keeps an associated `<label for>`;
  password inputs carry `autocomplete="current-password"` / `"new-password"`;
  nav anchors remain keyboard- and screen-reader navigable with `aria-current="page"`.
- **Change-password feedback:** inline `role="alert"` for errors (length/match/API),
  `role="status"` success alert, plus success toast — all announced.
- **Admin sub-cards:** labelled selects with proper option lists; the default-language
  select announces its purpose via `aria-describedby="#default-language-hint"`.
- **No fake controls:** non-admins cannot reach admin gating; System stays an honest
  reserved placeholder.

## 12. Regression evidence

| Check | Result |
|---|---|
| Frontend full suite | `214 passed / 0 failed` |
| Backend full suite | `706 passed / 11 skipped` |
| i18n parity | green |
| RTL guard (logical properties) | green |
| Router/sidebar/breadcrumb integration | untouched (route table, `settingsSectionKey`, shell unchanged) |

## 13. Gaps, deferred and not-applicable

- Gated capabilities are enumerated in §7 and are never mocked.
- No production or live data is touched; no migrations are added or altered.
- No new routing/UI framework; no icon/UX library introduced; design tokens reused throughout.

## 14. Conclusions

The Settings page now matches the eight-section target IA while keeping every
control genuinely backend-backed and every section routable. Language controls
live under **Language & Regional** and theme controls under **Appearance**
(including their admin-level application defaults, clearly separated from
personal preferences). **Security** is a real, tested control rather than a
placeholder, and **System** remains an honest reserved section rather than a
decorative one. No Phase 19 behavior was undone; the routing architecture built
in Phase 19 is preserved verbatim.

## 15. Acceptance decision

**ACCEPTED — COMPLETE.** All requirements #1–#21 are satisfied within scope:
Settings IA reorganized, no fake controls, no backend contract/schema changes,
no unrelated-phase work started, both regression suites green.

---
*Report based on `git status` snapshot at completion; nothing was committed, pushed, branched, reset, stashed, cleaned, reverted, or discarded.*