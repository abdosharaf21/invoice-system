/**
 * Account — profile display and change-password form.
 */

import { el, clear } from "../utils/dom.js";
import { authStore } from "../auth/store.js";
import { changePassword, fetchMe } from "../auth/endpoints.js";
import { toast } from "../components/toast.js";
import { roleLabel, roleClassToken, formatDateTime } from "../utils/format.js";
import { t } from "../i18n/index.js";

export async function renderAccount(container) {
  clear(container);
  document.body.classList.remove("login-body");

  container.appendChild(
    el("div", { className: "page-head" },
      el("div", null,
        el("h1", { className: "page-title" }, t("account.title")),
        el("div", { className: "page-head__meta" }, t("account.meta")),
      ),
    ),
  );

  let user = authStore.getUser();
  if (!user) {
    try {
      user = await fetchMe();
    } catch {
      // stay with the local snapshot
    }
  }
  if (!user) user = {};

  const role = (user.roles && user.roles[0]) || "viewer";

  container.appendChild(
    el("div", { className: "card" },
      el("div", { className: "card__header" }, el("div", { className: "section-title" }, t("account.profileSection"))),
      el("div", { className: "card__body" },
        el("dl", { className: "dl" },
          el("div", null, el("dt", null, t("account.thFullName")), el("dd", user.full_name || "—")),
          el("div", null, el("dt", null, t("account.thUsername")), el("dd", { className: "mono" }, user.username || "—")),
          el("div", null, el("dt", null, t("account.thEmail")), el("dd", user.email || "—")),
          el("div", null, el("dt", null, t("account.thRole")), el("dd", el("span", { className: `badge badge--${roleClassToken(role)}` }, roleLabel(role)))),
          el("div", null, el("dt", null, t("account.thCompanyId")), el("dd", { className: "mono" }, String(user.company_id ?? "—"))),
          el("div", null, el("dt", null, t("account.thLastLogin")), el("dd", formatDateTime(user.last_login_at))),
        ),
      ),
    ),
  );

  const errBox = el("div");
  const okBox = el("div");
  const form = el("form", { className: "form-narrow", onsubmit: (e) => { e.preventDefault(); submit(); } },
    el("div", { className: "field" },
      el("label", { for: "cur-pw" }, t("account.curPassword")),
      el("input", { className: "input", id: "cur-pw", type: "password", required: true, autocomplete: "current-password" }),
    ),
    el("div", { className: "field" },
      el("label", { for: "new-pw" }, t("account.newPassword")),
      el("input", { className: "input", id: "new-pw", type: "password", required: true, minlength: "6", autocomplete: "new-password" }),
    ),
    el("div", { className: "field" },
      el("label", { for: "new-pw2" }, t("account.confirmPassword")),
      el("input", { className: "input", id: "new-pw2", type: "password", required: true, autocomplete: "new-password" }),
    ),
    errBox,
    okBox,
    el("div", { className: "form-actions" },
      el("button", { className: "btn btn-primary", type: "submit" }, t("account.changePassword")),
    ),
  );

  container.appendChild(
    el("div", { className: "card" },
      el("div", { className: "card__header" }, el("div", { className: "section-title" }, t("account.securitySection"))),
      el("div", { className: "card__body" },
        el("p", { className: "text-sm text-secondary" }, t("account.securityHint")),
        form,
      ),
    ),
  );

  async function submit() {
    clear(errBox);
    clear(okBox);
    const current = form.querySelector("#cur-pw").value;
    const next = form.querySelector("#new-pw").value;
    const confirm = form.querySelector("#new-pw2").value;
    if (next.length < 6) {
      errBox.appendChild(el("div", { className: "alert alert--error", role: "alert" }, t("account.passwordMin")));
      return;
    }
    if (next !== confirm) {
      errBox.appendChild(el("div", { className: "alert alert--error", role: "alert" }, t("account.passwordMismatch")));
      return;
    }
    try {
      await changePassword(current, next);
      form.reset();
      okBox.appendChild(el("div", { className: "alert alert--success", role: "status" }, t("account.passwordUpdated")));
      toast(t("account.passwordUpdated"), { type: "success" });
    } catch (err) {
      errBox.appendChild(el("div", { className: "alert alert--error", role: "alert" }, err.message || t("account.passwordChanged")));
    }
  }
}