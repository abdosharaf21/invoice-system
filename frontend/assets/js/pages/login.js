/**
 * Login view — dailyaccounts-style professional authentication.
 */

import { el, clear, qs } from "../utils/dom.js";
import { login, fetchMe } from "../auth/endpoints.js";
import { getCurrentRole } from "../auth/store.js";

let formState = {
  email: "",
  password: "",
  error: null,
  busy: false,
};

export function renderLogin(container) {
  document.body.classList.add("login-body");
  clear(container);

  const card = el("div", { className: "login-center" },
    el("div", { className: "login-flagstrip" },
      el("span", { className: "r" }), el("span", { className: "w" }), el("span", { className: "b" })),
    el("div", { className: "login-card" },
      el("div", { className: "login-card__brand" },
        el("span", { className: "brand-mark" }, "E"),
        el("div", null,
          el("h1", { style: "font-size:1.05rem;font-weight:700;" }, "E-Invoice & Reconciliation"),
          el("div", { className: "text-xs text-muted" }, "Tax authority e-invoice compliance"),
        ),
      ),

      formState.error
        ? el("div", { className: "alert alert--error", role: "alert" },
            el("div", null,
              el("div", { className: "alert__title" }, "Sign in failed"),
              el("div", null, formState.error),
            ),
          )
        : null,

      el("form", { id: "login-form", novalidate: "" },
        el("div", { className: "form-field" },
          el("label", { className: "form-label", for: "login-email" }, "Email"),
          el("input", {
            id: "login-email",
            className: "input",
            type: "email",
            name: "email",
            autocomplete: "username",
            required: "required",
            value: "",
            placeholder: "you@company.example",
          }),
        ),
        el("div", { className: "form-field" },
          el("label", { className: "form-label", for: "login-password" }, "Password"),
          el("input", {
            id: "login-password",
            className: "input",
            type: "password",
            name: "password",
            autocomplete: "current-password",
            required: "required",
            value: "",
          }),
          el("div", { className: "form-hint" }, "Use the credentials issued by your company administrator."),
        ),
        el("button", { id: "login-submit", className: "btn btn-primary", style: "width:100%;", type: "submit" },
          "Sign in"),
        el("div", { className: "form-field--submit form-hint", style: "text-align:center;margin-block-start:0.75rem;" },
          "The E-Invoice & Reconciliation System is restricted to authorised personnel."),
      ),
    ),
  );

  container.appendChild(card);

  const form = qs("#login-form", container);
  const emailInput = qs("#login-email", container);
  const passInput = qs("#login-password", container);
  const submitBtn = qs("#login-submit", container);

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (formState.busy) return;

    const email = emailInput.value.trim();
    const password = passInput.value;
    formState.error = null;
    formState.busy = true;
    submitBtn.disabled = true;
    submitBtn.textContent = "Signing in…";

    try {
      await login(email, password);
      formState.busy = false;
      // Ensure the profile (roles) is fresh before navigating.
      await fetchMe().catch(() => null);
      const role = getCurrentRole();
      const target = role ? "#/dashboard" : "#/account";
      window.location.hash = target;
    } catch (err) {
      formState.error = err.message || "Unable to sign in. Please try again.";
      formState.busy = false;
      submitBtn.disabled = false;
      submitBtn.textContent = "Sign in";
      renderLogin(container); // re-render to surface the error alert
    }
  });

  emailInput.focus();
}

export function resetLoginState() {
  formState = { email: "", password: "", error: null, busy: false };
}