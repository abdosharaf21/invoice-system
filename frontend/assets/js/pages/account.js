/**
 * Account — profile display and change-password form.
 */

import { el, clear } from "../utils/dom.js";
import { authStore } from "../auth/store.js";
import { changePassword, fetchMe } from "../auth/endpoints.js";
import { toast } from "../components/toast.js";
import { roleLabel, formatDateTime } from "../utils/format.js";
import { escapeHtml } from "../utils/escape.js";

export async function renderAccount(container) {
  clear(container);
  document.body.classList.remove("login-body");

  container.appendChild(
    el("div", { className: "page-head" },
      el("div", null,
        el("h1", { className: "page-title" }, "Account"),
        el("div", { className: "page-head__meta" }, "Profile and security"),
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
    el("div", { className: "card", style: "margin-block-end:1.25rem;" },
      el("div", { className: "card__header" }, el("div", { className: "section-title" }, "Profile")),
      el("div", { className: "card__body" },
        el("dl", { className: "dl" },
          el("div", null, el("dt", null, "Full name"), el("dd", escapeHtml(user.full_name || "—"))),
          el("div", null, el("dt", null, "Username"), el("dd", { className: "mono" }, escapeHtml(user.username || "—"))),
          el("div", null, el("dt", null, "Email"), el("dd", escapeHtml(user.email || "—"))),
          el("div", null, el("dt", null, "Role"), el("dd", el("span", { className: `badge badge--role-${role}` }, roleLabel(role)))),
          el("div", null, el("dt", null, "Company ID"), el("dd", { className: "mono" }, String(user.company_id ?? "—"))),
          el("div", null, el("dt", null, "Last login"), el("dd", formatDateTime(user.last_login_at))),
        ),
      ),
    ),
  );

  const errBox = el("div");
  const okBox = el("div");
  const form = el("form", { onsubmit: (e) => { e.preventDefault(); submit(); } },
    el("div", { className: "field" },
      el("label", { for: "cur-pw" }, "Current password"),
      el("input", { id: "cur-pw", type: "password", required: true, autocomplete: "current-password" }),
    ),
    el("div", { className: "field" },
      el("label", { for: "new-pw" }, "New password"),
      el("input", { id: "new-pw", type: "password", required: true, minlength: "6", autocomplete: "new-password" }),
    ),
    el("div", { className: "field" },
      el("label", { for: "new-pw2" }, "Confirm new password"),
      el("input", { id: "new-pw2", type: "password", required: true, autocomplete: "new-password" }),
    ),
    errBox,
    okBox,
    el("div", { className: "form-actions" },
      el("button", { className: "btn btn-primary", type: "submit" }, "Change password"),
    ),
  );

  container.appendChild(
    el("div", { className: "card" },
      el("div", { className: "card__header" }, el("div", { className: "section-title" }, "Security")),
      el("div", { className: "card__body" },
        el("p", { className: "text-sm text-secondary" }, "Your password expires every 90 days and must differ from the previous one."),
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
      errBox.appendChild(el("div", { className: "alert alert--error" }, "New password must be at least 6 characters."));
      return;
    }
    if (next !== confirm) {
      errBox.appendChild(el("div", { className: "alert alert--error" }, "Passwords do not match."));
      return;
    }
    try {
      await changePassword(current, next);
      form.reset();
      okBox.appendChild(el("div", { className: "alert alert--success" }, "Password updated."));
      toast("Password updated", { type: "success" });
    } catch (err) {
      errBox.appendChild(el("div", { className: "alert alert--error" }, escapeHtml(err.message || "Password change failed.")));
    }
  }
}