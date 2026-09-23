/**
 * Login view — professional authentication.
 */

import { el, clear, qs } from "../utils/dom.js";
import { login, fetchMe } from "../auth/endpoints.js";
import { getCurrentRole } from "../auth/store.js";
import { getAppName } from "../settings/store.js";
import { t } from "../i18n/index.js";

let formState = {
  email: "",
  password: "",
  error: null,
  busy: false,
};

export function renderLogin(container) {
  document.body.classList.add("login-body");
  clear(container);

  let passInput;
  const pwToggle = el("button", {
    type: "button",
    className: "pw-toggle",
    "aria-pressed": "false",
    title: t("login.showPassword"),
  }, t("login.showPassword"));
  pwToggle.addEventListener("click", () => {
    const show = passInput.type === "password";
    passInput.type = show ? "text" : "password";
    pwToggle.setAttribute("aria-pressed", String(show));
    const label = show ? t("login.hidePassword") : t("login.showPassword");
    pwToggle.textContent = label;
    pwToggle.title = label;
    passInput.focus();
  });

  const layout = el("div", { className: "login-split" },
    el("div", { className: "login-brand-panel" },
      el("div", { className: "login-flagstrip" },
        el("span", { className: "r" }), el("span", { className: "w" }), el("span", { className: "b" })),
      el("div", { className: "login-brand-inner" },
        el("span", { className: "brand-mark brand-mark--lg" }, getAppName().charAt(0).toUpperCase()),
        el("h1", { className: "login-brand__title" }, t("login.brandTitle")),
        el("div", { className: "login-brand__sub" }, t("login.brandSub")),
        el("p", { className: "login-brand__notice" }, t("login.restricted")),
      ),
    ),
    el("div", { className: "login-form-panel" },
      el("div", { className: "login-card" },
        formState.error
          ? el("div", { className: "alert alert--error", role: "alert" },
              el("div", null,
                el("div", { className: "alert__title" }, t("login.signInFailed")),
                el("div", null, formState.error),
              ),
            )
          : null,

        el("form", { id: "login-form", novalidate: "" },
          el("div", { className: "form-field" },
            el("label", { className: "form-label", for: "login-email" }, t("login.email")),
            el("input", {
              id: "login-email",
              className: "input",
              type: "email",
              name: "email",
              autocomplete: "username",
              required: "required",
              value: formState.email,
              placeholder: t("login.emailPlaceholder"),
            }),
          ),
          el("div", { className: "form-field" },
            el("label", { className: "form-label", for: "login-password" }, t("login.password")),
            el("div", { className: "pw-wrap" },
              (passInput = el("input", {
                id: "login-password",
                className: "input",
                type: "password",
                name: "password",
                autocomplete: "current-password",
                required: "required",
                value: "",
              })),
              pwToggle,
            ),
            el("div", { className: "form-hint" }, t("login.hint")),
          ),
          el("button", { id: "login-submit", className: "btn btn-primary", type: "submit" },
            t("login.signIn")),
          el("div", { className: "form-field--submit form-hint", style: "text-align:center;margin-block-start:var(--space-3);" },
            t("login.restricted")),
        ),
      ),
    ),
  );

  container.appendChild(layout);

  const form = qs("#login-form", container);
  const emailInput = qs("#login-email", container);
  passInput = qs("#login-password", container);
  const submitBtn = qs("#login-submit", container);

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (formState.busy) return;

    const email = emailInput.value.trim();
    const password = passInput.value;
    formState.email = email; // preserve across the error re-render
    formState.error = null;
    formState.busy = true;
    submitBtn.disabled = true;
    submitBtn.textContent = t("login.signingIn");

    try {
      await login(email, password);
      formState.busy = false;
      // Ensure the profile (roles) is fresh before navigating.
      await fetchMe().catch(() => null);
      const role = getCurrentRole();
      const target = role ? "#/dashboard" : "#/account";
      window.location.hash = target;
    } catch (err) {
      formState.error = err.message || t("login.unable");
      formState.busy = false;
      submitBtn.disabled = false;
      submitBtn.textContent = t("login.signIn");
      renderLogin(container); // re-render to surface the error alert
    }
  });

  emailInput.focus();
}

export function resetLoginState() {
  formState = { email: "", password: "", error: null, busy: false };
}