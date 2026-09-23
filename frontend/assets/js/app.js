/**
 * Application bootstrap — hash router, auth guard, and the application shell
 * (sidebar, header, user menu, breadcrumbs). Single entry module.
 *
 * Navigation model:
 *  * unauthenticated → login page stands alone (no shell)
 *  * authenticated → shell is built once, then pages render into #app-main
 */

import { el, clear, icons } from "./utils/dom.js";
import { roleLabel } from "./utils/format.js";
import { authStore, getCurrentRole } from "./auth/store.js";
import { logout } from "./auth/endpoints.js";
import { setAuthFailureHandler } from "./api/client.js";
import { resolveRoute, canEnter, navSections, canSeeSection } from "./config/routes.js";
import { renderLogin, renderForbidden, renderNotFound } from "./pages/index.js";
import { renderSettings, settingsSectionKey } from "./pages/settings.js";
import { loadAppSettings, loadCompanySettings, loadUserPrefs, getAppName, getAppSubtitle, getCompanyName, getUserPrefs, getAppSettings, invalidateSettings } from "./settings/store.js";
import { initializeTheme, syncThemeFromSettings } from "./theme.js";
import { t, applyAppLocale, readPersistedLocale, resolveEffectiveLocale } from "./i18n/index.js";
import { toast } from "./components/toast.js";

const app = document.getElementById("app");

// Apply the theme before the first route paints (listens to OS changes when
// the preference is "system"). The no-flash bootstrap in index.html already
// set data-theme; this reconciles it with backend settings + OS once the app
// boots and later when settings are refreshed.
initializeTheme();

// Paint the app in the persisted language/direction before the first route —
// the i18n dictionaries ship with the bundle so this switch is synchronous.
applyAppLocale(readPersistedLocale() || "en");

boot();

function boot() {
  setAuthFailureHandler(handleAuthFailure);
  window.addEventListener("hashchange", () => handleRoute().catch((err) => console.error(err)));
  window.addEventListener("eis:localechange", onLocaleChange);

  // Skip link (Req 14): the anchor's href="#app-main" must never change the
  // hash — that would be treated as navigation by the router (no route owns
  // "app-main") and land the user on a 404. Intercept the click, keep the hash
  // stable, and move focus straight to the main landmark.
  document.addEventListener("click", (e) => {
    const skip = e.target && e.target.closest && e.target.closest("[data-skip-link]");
    if (!skip) return;
    e.preventDefault();
    const main = document.getElementById("app-main");
    (main || document.getElementById("app")).focus();
  });
  handleRoute().catch((err) => console.error(err));
}

/**
 * Immediate language switch (Req 5): rebuild the shell and re-render the
 * current route when `applyAppLocale` reports a real change. The rebuilt
 * `ensureShell` re-runs `reconcileLocale` and, thanks to the settings save
 * path refreshing user prefs first, resolves the same language — so no loop.
 * While no shell exists yet (boot-time reconcile) there is nothing to rebuild.
 */
let localeRebuilding = false;
function onLocaleChange() {
  if (localeRebuilding) return;
  const shell = document.querySelector(".app-shell");
  if (!shell) return;
  localeRebuilding = true;
  try {
    document.querySelectorAll(".app-shell").forEach((n) => n.remove());
    clear(app);
    handleRoute().catch((err) => console.error(err));
  } finally {
    localeRebuilding = false;
  }
}

/** A failed session (expired access token that could not be refreshed, or a
 * 401 on the retried request) clears the session and returns to login. */
function handleAuthFailure() {
  authStore.clear();
  invalidateSettings();
  toast(t("session.expiredBody"), { type: "error", duration: 6500 });
  window.location.hash = "#/login";
}

async function handleRoute() {
  const hash = window.location.hash || "#/login";
  const resolved = resolveRoute(hash);

  if (!authStore.isAuthenticated()) {
    renderLoginPage();
    return;
  }

  // Authenticated user.
  if (resolved && resolved.route.path === "login") {
    window.location.hash = "#/dashboard";
    return;
  }
  await ensureShell();

  const main = document.getElementById("app-main");
  // Make the landmark programmatically focusable so the skip link can land
  // focus on it. "app-main" is deliberately not a route, so focusing directly
  // here — rather than letting href="#app-main" change the hash — keeps the
  // hash router from treating the skip target as a navigation (404).
  if (main && !main.hasAttribute("tabindex")) main.setAttribute("tabindex", "-1");

  if (!resolved) {
    return renderPlain(main, renderNotFound);
  }
  if (!canEnter(resolved.route)) {
    return renderPlain(main, renderForbidden);
  }

  updateBreadcrumbs(resolved.route, resolved.params);
  highlightNav(resolved.route.path);

  clear(main);
  try {
    resolved.route.render(main, resolved.params);
  } catch (err) {
    console.error(err);
    main.appendChild(el("div", { className: "alert alert--error" }, err.message || t("common.unableLoad")));
  }
  document.title = `${t(titleKey(resolved.route, resolved.params))} · ${getAppName()}`;
  // Move the reading cursor to the rendered heading/content so keyboard and
  // screen-reader users get navigation context (Req 14). We only take over
  // when focus is still on the shell/body — i.e. nobody already interacted
  // in-page — so login's autofocus and in-page tabbing stay untouched.
  const focused = document.activeElement;
  if (!focused || focused === document.body) {
    const heading = main.querySelector("h1, h2[class*='page-heading'], .page-title");
    if (heading) {
      heading.setAttribute("tabindex", "-1");
      heading.focus({ preventScroll: true });
    }
  }
}

function titleKey(route, params) {
  return route.path === "settings/:section"
    ? settingsSectionKey(params && params[0]) || route.breadcrumb
    : route.breadcrumb;
}

function renderLoginPage() {
  clear(app);
  document.querySelectorAll(".app-shell").forEach((n) => n.remove());
  renderLogin(app, []);
}

function renderPlain(main, renderer) {
  clear(main);
  renderer(main, []);
  document.title = getAppName();
}

/* ----------------------------- Shell ----------------------------- */

async function ensureShell() {
  if (document.querySelector(".app-shell")) return;

  await Promise.all([
    loadAppSettings(),
    loadCompanySettings(),
    loadUserPrefs(),
  ]);
  syncThemeFromSettings();
  reconcileLocale();

  const shell = el("div", { className: "app-shell" },
    buildSidebar(),
    buildHeader(),
    el("main", { id: "app-main", className: "main" }),
  );
  clear(app);
  app.appendChild(shell);

  // Responsive drawer: hamburger + backdrop.
  const toggle = shell.querySelector(".header__menu-toggle");
  const sidebar = shell.querySelector(".sidebar");
  const backdrop = el("div", { className: "sidebar__backdrop" });
  const closeDrawer = () => {
    sidebar.classList.remove("is-open");
    toggle.setAttribute("aria-expanded", "false");
    backdrop.remove();
  };
  const openDrawer = () => {
    sidebar.classList.add("is-open");
    toggle.setAttribute("aria-expanded", "true");
    sidebar.after(backdrop);
  };
  backdrop.addEventListener("click", closeDrawer);
  const onDrawerKeydown = (e) => {
    if (e.key === "Escape") {
      e.preventDefault();
      closeDrawer();
      toggle.focus();
    }
  };
  document.addEventListener("keydown", onDrawerKeydown);
  toggle.addEventListener("click", () => {
    const open = sidebar.classList.toggle("is-open");
    if (open) openDrawer();
    else closeDrawer();
  });

  // User menu dropdown + keyboard navigation + outside click.
  const menuBtn = shell.querySelector(".user-menu__button");
  const menu = shell.querySelector(".user-menu__dropdown");
  const menuItems = () => Array.from(menu.querySelectorAll('[role="menuitem"]'));
  const moveMenuFocus = (dir) => {
    const items = menuItems();
    if (!items.length) return null;
    const cur = items.findIndex((elItem) => elItem === document.activeElement);
    const next = cur === -1
      ? (dir > 0 ? 0 : items.length - 1)
      : (cur + dir + items.length) % items.length;
    items[next].focus();
    return items[next];
  };
  const toggleMenu = (open, { focusFirst = false, restoreFocus = false } = {}) => {
    menu.classList.toggle("is-open", open);
    menuBtn.setAttribute("aria-expanded", String(open));
    if (open && focusFirst && menuItems()[0]) menuItems()[0].focus();
    if (!open && restoreFocus) menuBtn.focus();
  };
  menuBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    toggleMenu(!menu.classList.contains("is-open"));
  });
  menuBtn.addEventListener("keydown", (e) => {
    const isOpen = menu.classList.contains("is-open");
    if (e.key === "Escape") {
      if (isOpen) {
        e.preventDefault();
        e.stopPropagation();
        toggleMenu(false, { restoreFocus: true });
      }
      return;
    }
    if (isOpen) return; // arrow/enter handling lives on the menu while open
    if (e.key === "ArrowDown" || e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      toggleMenu(true, { focusFirst: true });
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      toggleMenu(true, { focusFirst: false });
      const items = menuItems();
      if (items.length) items[items.length - 1].focus();
    }
  });
  menu.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      e.preventDefault();
      e.stopPropagation();
      toggleMenu(false, { restoreFocus: true });
    } else if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      moveMenuFocus(e.key === "ArrowDown" ? 1 : -1);
    } else if (e.key === "Home" || e.key === "End") {
      e.preventDefault();
      const items = menuItems();
      const target = e.key === "Home" ? items[0] : items[items.length - 1];
      if (target) target.focus();
    } else if (e.key === "Tab") {
      // Closing on Tab keeps the rest of the page tabbable.
      toggleMenu(false);
    }
  });
  menuItems().forEach((item) => item.addEventListener("click", () => toggleMenu(false)));
  document.addEventListener("click", (e) => {
    if (menu.classList.contains("is-open") && !menu.contains(e.target) && e.target !== menuBtn && !menuBtn.contains(e.target)) {
      toggleMenu(false);
    }
  });
}

/**
 * Resolve the active locale from the authenticated user's profile language,
 * then the device-persisted choice, then the application default. The profile
 * preference wins so saved per-user languages survive reloads and devices.
 */
function reconcileLocale() {
  applyAppLocale(
    resolveEffectiveLocale(getUserPrefs(), getAppSettings(), readPersistedLocale()),
  );
}

function buildSidebar() {
  const role = getCurrentRole();
  const user = authStore.getUser() || {};
  const companyName = getCompanyName();
  const companyLabel = companyName || (user.company_id != null ? `${t("app.companyPrefixed")} ${user.company_id}` : t("app.noCompany"));

  const nav = el("nav", { id: "sidebar-nav", className: "sidebar__nav", "aria-label": t("nav.main") });
  for (const section of navSections) {
    if (!canSeeSection(section)) continue;
    nav.appendChild(el("div", { className: "nav-section" },
      el("div", { className: "nav-section__title" }, t(section.title)),
      el("div", null, ...section.items.map((item) =>
        el("a", { className: "nav-item", href: item.hash, dataset: { nav: item.hash } },
          el("span", { className: "nav-item__icon" }, icons[item.icon] || null),
          el("span", null, t(item.label)),
        ),
      )),
    ));
  }

  return el("aside", { className: "sidebar", "aria-label": t("nav.main") },
    el("div", { className: "sidebar__brand" },
      el("span", { className: "brand-mark" }, getAppName().charAt(0).toUpperCase()),
      el("div", null,
        el("div", { className: "sidebar__brand-title" }, getAppName()),
        el("div", { className: "sidebar__brand-sub" }, getAppSubtitle()),
      ),
    ),
    nav,
    el("div", { className: "sidebar__footer" },
      el("div", null, companyLabel),
      el("div", null, roleLabel(role)),
    ),
  );
}

function buildHeader() {
  const user = authStore.getUser() || {};
  const role = getCurrentRole();
  const companyName = getCompanyName();
  const companyLabel = companyName || (user.company_id != null ? `${t("app.companyPrefixed")} ${user.company_id}` : t("app.noCompany"));
  const initials = ((user.full_name || user.username || "U").trim().split(/\s+/).slice(0, 2).map((s) => s[0] || "").join("") || "U").toUpperCase();

  const dropdown = el("div", { className: "user-menu__dropdown", role: "menu" },
    el("div", { className: "user-menu__dropdown-header", "aria-hidden": "true" },
      el("strong", null, user.full_name || user.username || ""),
      el("div", { className: "text-xs text-muted" }, user.email || ""),
    ),
    el("button", { className: "menu-item", type: "button", role: "menuitem", onClick: () => { window.location.hash = "#/account"; } }, t("common.myAccount")),
    el("button", { className: "menu-item", type: "button", role: "menuitem", onClick: () => { window.location.hash = "#/settings"; } }, t("common.settings")),
    el("button", { className: "menu-item is-danger", type: "button", role: "menuitem", onClick: () => signOut() }, t("common.signOut")),
  );

  const header = el("header", { className: "header" },
    el("button", { className: "header__menu-toggle", type: "button", "aria-label": t("common.toggleNav"), "aria-controls": "sidebar-nav", "aria-expanded": "false" },
      el("span", null, icons.menu)),
    el("nav", { className: "breadcrumbs", id: "breadcrumbs", "aria-label": t("common.breadcrumb") },
      el("span", { className: "crumb-current" }, t("app.loading"))),
    el("div", { className: "header__spacer" }),
    el("div", { className: "header__company" },
      el("strong", null, companyLabel),
    ),
    el("div", { className: "user-menu" },
      el("button", { className: "user-menu__button", type: "button", "aria-haspopup": "menu", "aria-expanded": "false" },
        el("span", { className: "user-menu__avatar" }, initials),
        el("span", { className: "user-menu__label" },
          el("strong", null, user.full_name || user.username || t("common.user")),
          el("span", { className: "user-menu__role-badge" }, roleLabel(role)),
        ),
      ),
      dropdown,
    ),
  );
  return header;
}

function updateBreadcrumbs(route, params = []) {
  const crumb = document.getElementById("breadcrumbs");
  if (!crumb) return;
  clear(crumb);
  if (route.path === "settings/:section") {
    const crumbNode = (key) => el("span", null, t(key));
    const sep = () => el("span", { className: "text-muted" }, "/");
    // Administration is an admin-only section; non-admins reach settings via
    // the user menu, so the Administration crumb is skipped for them.
    if (getCurrentRole() === "admin") {
      crumb.appendChild(crumbNode("nav.administration"));
      crumb.appendChild(sep());
    }
    crumb.appendChild(crumbNode("nav.settings"));
    crumb.appendChild(sep());
    crumb.appendChild(el("span", { className: "crumb-current" },
      t(settingsSectionKey(params[0]) || route.breadcrumb)));
    return;
  }
  if (route.section) {
    crumb.appendChild(el("span", null, t(route.section)));
    crumb.appendChild(el("span", { className: "text-muted" }, "/"));
  }
  crumb.appendChild(el("span", { className: "crumb-current" }, t(route.breadcrumb)));
}

function highlightNav(path) {
  const active = document.querySelector(".nav-item.is-active");
  if (active) active.classList.remove("is-active");
  const base = path.split("/")[0];
  const link = document.querySelector(`.nav-item[data-nav="#/${base}"]`);
  if (link) link.classList.add("is-active");
}

async function signOut() {
  try {
    await logout();
  } finally {
    authStore.clear();
    invalidateSettings();
    window.location.hash = "#/login";
  }
}