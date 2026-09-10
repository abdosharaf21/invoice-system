/**
 * Application bootstrap — hash router, auth guard, and the application shell
 * (sidebar, header, user menu, breadcrumbs). Single entry module.
 *
 * Navigation model:
 *  * unauthenticated → login page stands alone (no shell)
 *  * authenticated → shell is built once, then pages render into #app-main
 */

import { el, clear, icons } from "./utils/dom.js";
import { escapeHtml } from "./utils/escape.js";
import { roleLabel } from "./utils/format.js";
import { authStore, getCurrentRole } from "./auth/store.js";
import { logout } from "./auth/endpoints.js";
import { setAuthFailureHandler } from "./api/client.js";
import { resolveRoute, canEnter, navSections, accountNav, canSeeSection } from "./config/routes.js";
import { renderLogin, renderForbidden, renderNotFound } from "./pages/index.js";

const app = document.getElementById("app");

boot();

function boot() {
  setAuthFailureHandler(() => {
    authStore.clear();
    window.location.hash = "#/login";
  });
  window.addEventListener("hashchange", handleRoute);
  handleRoute();
}

function handleRoute() {
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
  ensureShell();

  const main = document.getElementById("app-main");

  if (!resolved) {
    return renderPlain(main, renderNotFound);
  }
  if (!canEnter(resolved.route)) {
    return renderPlain(main, renderForbidden);
  }

  updateBreadcrumbs(resolved.route);
  highlightNav(resolved.route.path);

  clear(main);
  try {
    resolved.route.render(main, resolved.params);
  } catch (err) {
    console.error(err);
    main.appendChild(el("div", { className: "alert alert--error" }, escapeHtml(err.message || "Rendering failed.")));
  }
  document.title = `${resolved.route.breadcrumb} · E-Invoice & Reconciliation`;
}

function renderLoginPage() {
  clear(app);
  document.querySelectorAll(".app-shell").forEach((n) => n.remove());
  renderLogin(app, []);
}

function renderPlain(main, renderer) {
  clear(main);
  renderer(main, []);
  document.title = "E-Invoice & Reconciliation";
}

/* ----------------------------- Shell ----------------------------- */

function ensureShell() {
  if (document.querySelector(".app-shell")) return;

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
    backdrop.remove();
  };
  toggle.addEventListener("click", () => {
    const open = sidebar.classList.toggle("is-open");
    if (open) {
      sidebar.after(backdrop);
      backdrop.addEventListener("click", closeDrawer);
    } else {
      closeDrawer();
    }
  });

  // User menu dropdown + outside click.
  const menuBtn = shell.querySelector(".user-menu__button");
  const menu = shell.querySelector(".user-menu__dropdown");
  menuBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    menu.classList.toggle("is-open");
  });
  document.addEventListener("click", (e) => {
    if (menu.classList.contains("is-open") && !menu.contains(e.target) && e.target !== menuBtn && !menuBtn.contains(e.target)) {
      menu.classList.remove("is-open");
    }
  });
}

function buildSidebar() {
  const role = getCurrentRole();
  const user = authStore.getUser() || {};

  const nav = el("nav", { className: "sidebar__nav", "aria-label": "Main navigation" });
  for (const section of navSections) {
    if (!canSeeSection(section)) continue;
    nav.appendChild(el("div", { className: "nav-section" },
      el("div", { className: "nav-section__title" }, section.title),
      el("div", null, ...section.items.map((item) =>
        el("a", { className: "nav-item", href: item.hash, dataset: { nav: item.hash } },
          el("span", { className: "nav-item__icon" }, icons[item.icon] || null),
          el("span", null, item.label),
        ),
      )),
    ));
  }

  return el("aside", { className: "sidebar", "aria-label": "Application" },
    el("div", { className: "sidebar__brand" },
      el("span", { className: "brand-mark" }, "E"),
      el("div", null,
        el("div", { className: "sidebar__brand-title" }, "E-Invoice & Reconciliation"),
        el("div", { className: "sidebar__brand-sub" }, "Tax authority compliance"),
      ),
    ),
    nav,
    el("div", { className: "sidebar__footer" },
      el("div", null, `Company ${user.company_id != null ? `#${user.company_id}` : "—"}`),
      el("div", null, escapeHtml(roleLabel(role))),
    ),
  );
}

function buildHeader() {
  const user = authStore.getUser() || {};
  const role = getCurrentRole();
  const initials = ((user.full_name || user.username || "U").trim().split(/\s+/).slice(0, 2).map((s) => s[0] || "").join("") || "U").toUpperCase();

  const dropdown = el("div", { className: "user-menu__dropdown" },
    el("div", { className: "user-menu__dropdown-header" },
      el("strong", null, escapeHtml(user.full_name || user.username || "")),
      el("div", { className: "text-xs text-muted" }, escapeHtml(user.email || "")),
    ),
    el("button", { className: "menu-item", type: "button", onClick: () => { window.location.hash = "#/account"; } }, "My account"),
    el("button", { className: "menu-item is-danger", type: "button", onClick: () => signOut() }, "Sign out"),
  );

  const header = el("header", { className: "header" },
    el("button", { className: "header__menu-toggle", type: "button", "aria-label": "Toggle navigation" },
      el("span", null, icons.menu)),
    el("nav", { className: "breadcrumbs", id: "breadcrumbs", "aria-label": "Breadcrumb" },
      el("span", { className: "crumb-current" }, "Load")),
    el("div", { className: "header__spacer" }),
    el("div", { className: "header__company" },
      el("strong", null, user.company_id != null ? `Payments & Reports · Company ${user.company_id}` : "Payments & Reports"),
    ),
    el("div", { className: "user-menu" },
      el("button", { className: "user-menu__button", type: "button", "aria-haspopup": "menu", "aria-expanded": "false" },
        el("span", { className: "user-menu__avatar" }, initials),
        el("span", { className: "user-menu__label" },
          el("strong", null, escapeHtml((user.full_name || user.username || "User"))),
          el("span", { className: "user-menu__role-badge" }, escapeHtml(roleLabel(role))),
        ),
      ),
      dropdown,
    ),
  );
  return header;
}

function updateBreadcrumbs(route) {
  const crumb = document.getElementById("breadcrumbs");
  if (!crumb) return;
  clear(crumb);
  if (route.section) {
    crumb.appendChild(el("span", null, route.section));
    crumb.appendChild(el("span", { className: "text-muted" }, "/"));
  }
  crumb.appendChild(el("span", { className: "crumb-current" }, route.breadcrumb));
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
    window.location.hash = "#/login";
  }
}