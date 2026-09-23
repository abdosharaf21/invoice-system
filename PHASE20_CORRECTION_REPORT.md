# Phase 20 — Settings Cleanup & Email Capability Audit (Correction Pass)

Status: **Complete**
Supersedes the interim claims in `PHASE20_REPORT.md` where they conflict with this
report. This correction pass was requested to re-audit the Settings surface,
resolve the duplicate Appearance/Language controls, fix the manual-refresh bug on
language switch, remove pages the client never requested in this scope
(Security, My Profile, page-size), make the System tab honest, and verify whether
real email sending actually exists. No migrations were added and no live database
data was touched.

---

## 1. What was removed and why

| Removed | Where | Why |
| --- | --- | --- |
| **Security page** (`#/settings/security`) | Settings nav, `mountSecuritySection`, its route mapping | Out of the agreed Settings scope; the "user-facing" article list never included a Security page. The capability still exists and stays reachable: the standalone **Account** page (`#/account`, `pages/account.js`) keeps the change-password form backed by the real `PUT /api/auth/change-password` (admin-gated server-side). No backend capability was deleted — only the redundant Settings sub-page and its unused `settings.security`/`nav.security` copy moved out of reach of the (unrequested) Settings entry. |
| **My Profile page** (`#/settings/profile`) | Settings nav, `mountProfileSection`, its route mapping | Same rationale: Settings is for application/account configuration; personal identity/credentials live on the standalone Account page that was already delivered. Removing it also removed the duplicate profile controls that overlapped with Account. |
| **Page-size preference** (`pagination_size`) | General settings field + `readAppForm` extraction | Nothing in the product consumes a per-user page size — every table hard-codes `LIMITS.defaultPageSize` (50) via `config.js:45`. Keeping a stored-but-unused preference is dead state, so the control (which never had any effect) is gone. The `pagination_size` column/API remain untouched server-side for forward-compatibility; the frontend simply no longer edits it. |

Consequence: the removed `#/settings/security` and `#/settings/profile` sub-routes no
longer resolve. An admin navigating to either is redirected to
`#/settings/general`; a non-admin to `#/settings/appearance`. No 404, no empty
page.

## 2. Final Settings navigation (all authenticated users see it)

The Settings nav (`settings.js`, `SECTION_META`) now contains exactly:

1. **General** — application name/subtitle + regional formatting defaults, save as one action (admin-editable).
2. **Organization** — company profile (admin-editable).
3. **Email & Notifications** — read-only email status + test form (admin-gated render).
4. **Appearance** — Personal theme (every user) + Application default theme (admin).
5. **Language & Regional** — Personal language/date/number/timezone (every user) + Application default language (admin).
6. **System** — reserved state (see §4).

The top-level nav entry remains "Settings" with active section highlighting and
`aria-current="page"` on the active sub-route.

## 3. Duplicate Appearance / Language controls — resolution

Both pairs were **genuinely different scopes** and both were backend-supported
(`/api/settings/user` for personal prefs, `/api/settings/application` for
application defaults), so both were kept — and disambiguated clearly instead of
deleted:

- **Personal theme** → `settings.labelPersonalTheme` (select `name="theme"`) with hint `settings.themePersonalHint` = *"Applies to this account only."*
- **Application defaults card** → "Application defaults → Default theme" (select `name="default_theme"`) with hint `settings.themeAppHint` = *"Application-wide default used until a user chooses a personal theme."* Attached via `aria-describedby="default-theme-hint"`.
- **Personal language** → `settings.labelPersonalLanguage` (select `name="language"`) with hint `settings.languagePersonalHint` = *"Interface language for this account."*
- **Application defaults card → Default language** (select `name="default_language"`) with hint `#default-language-hint`.

The admin cards render only when `isAdmin`, under an "Application defaults" card
that no longer claims to be the personal control.

## 4. "System" tab — capability result

The backend exposes **(no) system-level controls**. Previously the page showed an
empty placeholder. It now renders an intentional reserved state instead of a
broken/blank section: `settings.systemUnavailable` (*"System settings are not
currently available."*) + `settings.systemHint` (reserved for future administrative
functionality), with `role="status"` and **no** fake buttons/inputs/selects.

```
capability result: NO backend system-administration API exists
handled by:       an honest reserved-state card (no invented controls)
```

## 5. Language-switch bug — root cause and fix

**Symptom:** after saving a different language in Settings, the UI changed only
after a manual page refresh.

**Root cause:** the old Language & Regional section installed a `change`-event
preview listener that called `applyAppLocale(lang, { silent: true })` the moment a
user picked a language in the dropdown — *before saving*. `applyAppLocale` mutates
the module-level `currentLocale` synchronously, so when the Save handler later
called the plain `applyAppLocale(payload.language)`, the engine saw
`payload.language === currentLocale` and concluded *no change* → it never emitted
`eis:localechange` → `app.js`'s `onLocaleChange` never ran → the shell never
rebuilt → only a manual refresh (which re-reads localStorage `eis:lang`) showed
the switch.

**Fix:** removed the silent change-preview listener. The save path is now the only
place the language changes, so the change is detected and the rebuild event is
dispatched. The shell rebuild (`onLocaleChange`) teardown/clear only the `.app-shell`
and re-run `handleRoute()`; the route/hash is never rewritten and
`reconcileLocale` resolves the just-saved language (prefs were force-refreshed
before `applyAppLocale`), so there is no loop.

Result (verified in a real browser, and in unit tests): selecting Arabic → Save
rebuilds the shell instantly — `lang="ar"`, `dir="rtl"`, sidebar, breadcrumb and
section heading Arabic, URL hash unchanged, **no page reload**; the same holds for
EN, instantly back to `ltr`.

## 6. Additional bug found during browser verification

`fieldInput` (in the module under correction) built `<select>` elements with a
`value` **attribute** but never set `selected` on the matching `<option>`.
Browsers ignore `value` on a `<select>` for pre-selection and default to the first
option — so any saved non-default value (e.g. language `ar`, theme `dark`,
`Africa/Cairo` timezone) always rendered as the *first* list option, making the
form appear to revert user preferences on every visit. Fixed by assigning
`sel.value` after the options are appended (settings.js, `fieldInput`). Covered by
a new unit test asserting saved `dark`/`ar`/`Africa/Cairo` pre-select correctly.

## 7. Email capability audit — result: REAL EMAIL SENDING EXISTS

**`REAL EMAIL SENDING: YES`** — the backend ships a working SMTP implementation
(`backend/modules/email/`), it is not a stub:

- `provider.py` sends real mail over the Python stdlib `smtplib` (TLS/SSL modes).
- `service.py` implements `send_test`, `resend_delivery`, `list_deliveries`, and `notify_run_summary` (per-run reconciliation summary e-mail, best-effort).
- `routes.py` exposes admin-gated (`require_admin`) endpoints:
  - `GET  /api/email/status` — read-only status + supported events.
  - `POST /api/email/test` — send a test message to one address.
- Reconciliation wires `notify_run_summary` at `reconciliation/service.py:457`.

Configuration (environment only, never exposed via the API):
`EMAIL_ENABLED`, `EMAIL_PROVIDER` (`smtp` default / `gmail`), `EMAIL_HOST`,
`EMAIL_PORT` (default 587), `EMAIL_USERNAME`, `EMAIL_PASSWORD`, `EMAIL_FROM`,
`EMAIL_USE_TLS`, `EMAIL_USE_SSL` (`backend/config.py`). `EMAIL_ENABLED` defaults to
`false`; the pre-existing frontend disabled-banner text ("Email sending is
currently disabled") is therefore truthful. **Gmail** is supported as plain SMTP
via `smtp.gmail.com` with an app password — no special Gmail code path is needed.

Conclusion: the Settings → Email & Notifications read-only UI is accurate as-is.
No changes were required; the section truthfully shows disabled status, provider,
SMTP host:port, from-address, security mode, and disables the test form until email
is enabled.

## 8. Tests run and results

| Suite | Command | Result |
| --- | --- | --- |
| Frontend unit/integration | `npm test` (frontend/) | **220 passed / 0 failed** |
| Backend | `../.venv/bin/python -m pytest -q` (backend/) | **706 passed / 11 skipped** |
| Browser (real Chromium, headless, mocked API) | `playwright-core` script | **38 / 38 checks passed** |

Frontend tests added/changed: nav lists, section-switch to Appearance, non-admin
redirect, no-Security/Profile/page-size coverage, Appearance & Language scopes,
System reserved state, and EN→AR→EN immediate-switch tests with the
`installLocaleRebuild` helper. Added: saved non-default value pre-selection test.

Browser verification covered: Settings opens; exact 6-item admin nav with no
Security/My profile; exactly one personal + one application-default control for
theme and language (with hints/aria); no `pagination_size` anywhere; EN→AR and
AR→EN immediate switches (lang/dir/nav/breadcrumb/heading, hash stable, zero page
reloads); System reserved state with no controls; Email truthful disabled state;
removed-route fallback; standalone Account (`#/account`) still renders the profile
and change-password form; General section renders with no page-size field.

## 9. Files changed

- `frontend/assets/js/pages/settings.js` — removed Security/My Profile/page-size, added hints + personal labels, System reserved state, locale-switch fix, `fieldInput` pre-selection fix.
- `frontend/assets/js/i18n/en.js`, `frontend/assets/js/i18n/ar.js` — key removals/additions in lockstep (parity preserved).
- `frontend/test/settings.test.js` — updated + new tests; `installLocaleRebuild` helper.
- `frontend/test/i18n.test.js`, `frontend/test/rtl-guard.test.js` — unchanged but still enforce key parity and RTL-safe (logical-property) CSS strings; both green.

## 10. Constraints honored

- No migrations added/edited for this cleanup; no live development/production database
  data was created, modified or deleted (browser verification used scripted HTTP mocks).
- No backend capability was faked: System = honest reserved state; email = audited as real.
- `PHASE19_REPORT.md` / `PHASE20_REPORT.md` not rewritten; no commits/pushes/branches were
  made. `git status` left as-is.

## 11. Final UI cleanup (follow-up pass)

A follow-up, narrowly-scoped UI pass on the same corrected module removed the last
two duplicate controls and the now-obsolete reserved System page.

**Duplicate Appearance control removed** — the admin-only "Application defaults →
Default theme" card (`default_theme` + `#default-theme-hint`) was deleted from the
Appearance section. Appearance now renders exactly **one** theme-changing control:
the personal theme select (`[name="theme"]`, "Personal theme", hint "Applies to
this account only."). Saved-theme persistence, the `light`/`dark`/`system`
behavior, and backend theme storage are unchanged.

**Duplicate Language control removed** — the admin-only "Application defaults →
Default language" card (`default_language` + `#default-language-hint`) was deleted
from Language & Regional. The section now renders exactly **one** language-changing
control (the personal `[name="language"]` select). The immediate EN↔AR lifecycle is
fully preserved: `documentElement.lang`/`dir`, sidebar/breadcrumb/current-section
rebuilds, hash stability, zero page reloads, and persistence after reload are all
unchanged and re-verified. Only the personal save form POSTs/PUTs
`/api/settings/user`; no second language mechanism was introduced.

**System Settings page removed completely** — the reserved state was not wanted. The
System nav item, `mountSystemSection`, `settings.navSystem`/`systemMeta`/
`systemUnavailable`/`systemHint` translations, and associated tests were removed.
The `settings/:section` route remains generic; navigating to the old
`#/settings/system` now follows the existing invalid-section fallback (admin →
`#/settings/general`, non-admin → `#/settings/appearance`). No replacement empty
page was added and no fake System settings were created. `loadAppDefaults` /
`mountApplicationDefaultsCard` / `APP_THEMES` and the 
`labelDefaultTheme`/`themeAppHint`/`labelDefaultLanguage`/`defaultLanguageHint`/
`appDefaultsTitle` translations were removed as dead code.

**Final verification results**

| Suite | Result |
| --- | --- |
| Frontend unit/integration (`npm test`) | **220 passed / 0 failed** |
| Backend (`pytest -q`) | **706 passed / 11 skipped** |
| Real Chromium browser (scripted `/api` mocks) | **41 / 41 checks passed** |

Real-browser checks covered (admin role): Settings sub-nav is exactly
General · Organization · Email & Notifications · Appearance · Language & Regional
(no System, no My profile, no Security); Appearance shows exactly one theme control
(no `default_theme`, no "Default theme"/"Application defaults"/`#default-theme-hint`);
Language & Regional shows exactly one language control (no `default_language`), with
EN→AR and AR→EN switching immediately (correct `lang`/`dir`, sub-nav/sidebar/
breadcrumb/current section updated, hash unchanged, zero page reloads, a single
language control after each rebuild); `#/settings/system` redirects admin to
`#/settings/general` with no System text anywhere; top-level sidebar nav has no
System entry; Email disabled banner remains truthful; `#/account` still renders the
profile + change-password form; General renders with no page-size field.

Final visible structure of Settings:

```
Settings
├── General
├── Organization
├── Email & Notifications
├── Appearance
└── Language & Regional
```

No backend, database, migration, auth, email, Account/Profile, theme-engine,
language-engine, or routing (beyond removing System) code was changed; nothing was
committed or pushed.