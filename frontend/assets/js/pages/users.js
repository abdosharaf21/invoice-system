/**
 * Users (admin only) — enterprise user table with create, edit, activate /
 * deactivate, password reset and delete, backed by the /api/users blueprint.
 */

import { el, clear, showLoading, showError, showEmpty } from "../utils/dom.js";
import { listUsers, createUser, updateUser, resetUserPassword, activateUser, deactivateUser, deleteUser } from "../services/users.js";
import { openModal } from "../components/modal.js";
import { renderMenuButton } from "../components/dropdown.js";
import { toast } from "../components/toast.js";
import { roleLabel, roleClassToken, statusClassToken, statusLabel, formatDateTime } from "../utils/format.js";
import { isValidEmail } from "../utils/validation.js";
import { t } from "../i18n/index.js";

const ROLES = ["admin", "accountant", "manager", "viewer"];

export async function renderUsers(container) {
  clear(container);
  document.body.classList.remove("login-body");

  container.appendChild(
    el("div", { className: "page-head" },
      el("div", null,
        el("h1", { className: "page-title" }, t("users.title")),
        el("div", { className: "page-head__meta" }, t("users.meta")),
      ),
      el("div", { className: "page-head__actions" },
        el("button", { className: "btn btn-primary", onClick: () => openUserModal() }, t("users.add")),
      ),
    ),
  );

  const box = el("div");
  container.appendChild(box);
  await loadUsers(box);

  async function loadUsers(target) {
    showLoading(target, t("users.loading"));
    try {
      const res = await listUsers();
      const users = res || [];
      clear(target);
      if (!users.length) {
        showEmpty(target, t("users.noUsers"), {
          action: t("users.add"),
          onAction: () => openUserModal(),
        });
        return;
      }
      target.appendChild(renderTable(users));
    } catch (err) {
      showError(target, err.message || t("users.failedLoad"), { onRetry: () => loadUsers(target) });
    }
  }

  function renderTable(users) {
    const table = el("table", { className: "etable" },
      el("thead", null, el("tr", null,
        el("th", null, t("users.thFullName")),
        el("th", null, t("users.thUsername")),
        el("th", null, t("users.thEmail")),
        el("th", null, t("users.thRole")),
        el("th", null, t("users.thCompany")),
        el("th", null, t("users.thStatus")),
        el("th", null, t("users.thLastLogin")),
        el("th", null, t("common.actions")),
      )),
    );
    const tbody = el("tbody");
    for (const u of users) {
      const role = (u.roles && u.roles[0]) || "viewer";
      const status = u.is_active ? "active" : "inactive";
      const company = companyLabel(u);
      const tr = el("tr", null,
        el("td", null,
          el("div", { className: "user-cell" },
            el("span", { className: "avatar", "aria-hidden": "true" }, initialsOf(u)),
            el("span", { className: "user-cell__name" },
              el("strong", null, u.full_name || u.username)),
          ),
        ),
        el("td", { className: "mono" }, u.username),
        el("td", null, u.email),
        el("td", null, el("span", { className: `badge badge--${roleClassToken(role)}` }, roleLabel(role))),
        el("td", null, el("span", { className: "mono text-sm", title: company }, company)),
        el("td", null, el("span", { className: `badge badge--${statusClassToken(status)}` }, statusLabel(status))),
        el("td", null, formatDateTime(u.last_login_at)),
      );
      const actions = el("td", { className: "actions-cell" });
      renderMenuButton(actions, {
        label: t("users.actions"),
        items: [
          { label: t("common.edit"), onClick: () => openUserModal(u) },
          u.is_active
            ? { label: t("users.deactivate"), onClick: () => toggleActive(u, false) }
            : { label: t("users.activate"), onClick: () => toggleActive(u, true) },
          { label: t("users.password"), onClick: () => openPasswordModal(u) },
          { label: t("common.delete"), danger: true, onClick: () => confirmDelete(u) },
        ],
      });
      tr.appendChild(actions);
      tbody.appendChild(tr);
    }
    table.appendChild(tbody);
    return el("div", { className: "card card--table" },
      el("div", { className: "table-wrap" }, table),
    );
  }

  async function toggleActive(u, activate) {
    try {
      await (activate ? activateUser(u.id) : deactivateUser(u.id));
      toast(t(activate ? "users.activated" : "users.deactivated", { name: u.username }), { type: "success" });
      loadUsers(box);
    } catch (err) {
      toast(err.message || t("users.actionFailed"), { type: "error" });
    }
  }

  function confirmDelete(u) {
    openModal({
      title: t("users.deleteTitle", { name: u.username }),
      body: el("p", null, t("users.deleteBody", { email: u.email })),
      actions: [
        { label: t("common.cancel"), variant: "secondary", onClick: (m) => m.close() },
        {
          label: t("common.delete"),
          variant: "danger",
          onClick: async (m) => {
            try {
              await deleteUser(u.id);
              m.close();
              toast(t("users.deleted", { name: u.username }), { type: "success" });
              loadUsers(box);
            } catch (err) {
              toast(err.message || t("users.deleteFailed"), { type: "error" });
            }
          },
        },
      ],
    });
  }

  function openUserModal(user) {
    const isEdit = Boolean(user);
    const state = {
      username: user ? user.username : "",
      email: user ? user.email : "",
      first_name: user ? (user.first_name || "") : "",
      last_name: user ? (user.last_name || "") : "",
      company_id: user ? (user.company_id != null ? String(user.company_id) : "") : "",
      role: (user && user.roles && user.roles[0]) || "viewer",
      status: user ? (user.is_active ? "active" : "inactive") : "active",
      password: "",
    };

    const errBox = el("div");
    const form = el("form", { onsubmit: (e) => { e.preventDefault(); submit(m); } },
      el("div", { className: "field" },
        el("label", { for: "user-username" }, t("users.labelUsername")),
        el("input", { className: "input", type: "text", id: "user-username", value: state.username, required: true, "data-field": "username" }),
      ),
      el("div", { className: "field" },
        el("label", { for: "user-email" }, t("users.labelEmail")),
        el("input", { className: "input", type: "email", id: "user-email", value: state.email, required: true, "data-field": "email" }),
      ),
      el("div", { className: "field-row" },
        el("div", { className: "field", style: "flex:1;" },
          el("label", { for: "user-first-name" }, t("users.labelFirstName")),
          el("input", { className: "input", type: "text", id: "user-first-name", value: state.first_name, "data-field": "first_name" }),
        ),
        el("div", { className: "field", style: "flex:1;" },
          el("label", { for: "user-last-name" }, t("users.labelLastName")),
          el("input", { className: "input", type: "text", id: "user-last-name", value: state.last_name, "data-field": "last_name" }),
        ),
      ),
      el("div", { className: "field-row" },
        el("div", { className: "field", style: "flex:1;" },
          el("label", { for: "user-role" }, t("users.labelRole")),
          el("select", { className: "select", id: "user-role", "data-field": "role" }, ROLES.map((r) => el("option", { value: r, selected: r === state.role }, roleLabel(r)))),
        ),
        el("div", { className: "field", style: "flex:1;" },
          el("label", { for: "user-company-id" }, t("users.labelCompanyId")),
          el("input", { className: "input", type: "text", id: "user-company-id", value: state.company_id, placeholder: t("users.companyIdPlaceholder"), "data-field": "company_id" }),
        ),
      ),
      el("div", { className: "field-row" },
        el("div", { className: "field", style: "flex:1;" },
          el("label", { for: "user-status" }, t("users.labelStatus")),
          el("select", { className: "select", id: "user-status", "data-field": "status" },
            el("option", { value: "active", selected: state.status === "active" }, t("users.active")),
            el("option", { value: "inactive", selected: state.status === "inactive" }, t("users.inactive")),
          ),
        ),
        !isEdit
          ? el("div", { className: "field", style: "flex:1;" },
            el("label", { for: "user-password" }, t("users.labelPassword")),
            el("input", { className: "input", type: "password", id: "user-password", value: state.password, required: true, minlength: "6", "data-field": "password" }),
          )
          : el("div", { className: "field", style: "flex:1;" },
            el("label", { for: "user-password" }, t("users.labelPassword")),
            el("input", { className: "input", type: "password", id: "user-password", value: state.password, disabled: true, placeholder: t("users.passwordHint"), "data-field": "password" }),
          ),
      ),
      errBox,
    );

    const m = openModal({
      title: isEdit ? t("users.editTitle", { name: user.username }) : t("users.addTitle"),
      body: form,
      actions: [
        { label: t("common.cancel"), variant: "secondary", onClick: (modal) => modal.close() },
        {
          label: isEdit ? t("common.saveChanges") : t("users.create"),
          variant: "primary",
          onClick: async (modal) => submit(modal),
        },
      ],
    });

    async function submit(modal) {
      clear(errBox);
      const field = (name) => form.querySelector(`[data-field="${name}"]`);
      const payload = {
        username: field("username").value.trim(),
        email: field("email").value.trim(),
        first_name: field("first_name").value.trim(),
        last_name: field("last_name").value.trim(),
        company_id: field("company_id").value.trim(),
        roles: [field("role").value],
        status: field("status").value,
      };
      if (!isValidEmail(payload.email)) {
        errBox.appendChild(formError(t("common.validEmail")));
        return;
      }
      if (payload.company_id === "" && payload.roles[0] !== "admin") {
        payload.company_id = null;
      }
      try {
        if (isEdit) {
          await updateUser(user.id, payload);
          toast(t("users.updated"), { type: "success" });
        } else {
          payload.password = form.querySelector('[data-field="password"]').value;
          await createUser(payload);
          toast(t("users.created"), { type: "success" });
        }
        modal.close();
        loadUsers(box);
      } catch (err) {
        errBox.appendChild(formError(err.message || t("users.requestFailed")));
      }
    }
  }

  function openPasswordModal(user) {
    const state = { password: "" };
    const errBox = el("div");
    const form = el("form", { onsubmit: (e) => { e.preventDefault(); submit(m); } },
      el("p", null, t("users.setNewPassword", { name: user.username })),
      el("div", { className: "field" },
        el("label", { for: "user-new-password" }, t("users.newPasswordLabel")),
        el("input", { className: "input", type: "password", id: "user-new-password", value: state.password, required: true, minlength: "6", "data-field": "password" }),
      ),
      errBox,
    );

    const m = openModal({
      title: t("users.resetTitle", { name: user.username }),
      body: form,
      actions: [
        { label: t("common.cancel"), variant: "secondary", onClick: (modal) => modal.close() },
        {
          label: t("users.resetPassword"),
          variant: "primary",
          onClick: (modal) => submit(modal),
        },
      ],
    });

    async function submit(modal) {
      clear(errBox);
      const pw = form.querySelector('[data-field="password"]').value;
      if (!pw || pw.length < 6) {
        errBox.appendChild(formError(t("users.passwordMin")));
        return;
      }
      try {
        await resetUserPassword(user.id, pw);
        modal.close();
        toast(t("users.passwordReset"), { type: "success" });
      } catch (err) {
        errBox.appendChild(formError(err.message || t("users.resetFailed")));
      }
    }
  }
}

/** Modal inline error banner — announced to assistive technology on insert. */
function formError(message) {
  return el("div", { className: "alert alert--error", role: "alert" }, message);
}

/** Avatar initials from the display name (never from markup). */
function initialsOf(u) {
  const base = String(u.full_name || u.username || "").trim();
  const parts = base.split(/\s+/).filter(Boolean).slice(0, 2);
  return parts.map((p) => p.charAt(0).toUpperCase()).join("") || "?";
}

/**
 * Company label: the backend provides company_name when the collection is
 * enriched; otherwise fall back to a prefixed id, never an invented name
 * (the users API carries company_id only).
 */
function companyLabel(u) {
  if (u.company_name) return String(u.company_name);
  if (u.company_id != null) return `${t("app.companyPrefixed")} ${u.company_id}`;
  return "—";
}