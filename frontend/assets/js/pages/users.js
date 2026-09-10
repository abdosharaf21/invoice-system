/**
 * Users (admin only) — enterprise user table with create, edit, activate /
 * deactivate, password reset and delete, backed by the /api/users blueprint.
 */

import { el, clear, showLoading, showError } from "../utils/dom.js";
import { listUsers, createUser, updateUser, resetUserPassword, activateUser, deactivateUser, deleteUser } from "../services/users.js";
import { openModal } from "../components/modal.js";
import { toast } from "../components/toast.js";
import { roleLabel, formatDateTime } from "../utils/format.js";
import { escapeHtml } from "../utils/escape.js";
import { isValidEmail } from "../utils/validation.js";

const ROLES = ["admin", "accountant", "manager", "viewer"];

export async function renderUsers(container) {
  clear(container);
  document.body.classList.remove("login-body");

  container.appendChild(
    el("div", { className: "page-head" },
      el("div", null,
        el("h1", { className: "page-title" }, "Users"),
        el("div", { className: "page-head__meta" }, "Accounts of this platform · administrator only"),
      ),
      el("div", { className: "page-head__actions" },
        el("button", { className: "btn btn-primary", onClick: () => openUserModal() }, "Add user"),
      ),
    ),
  );

  const box = el("div");
  container.appendChild(box);
  await loadUsers(box);

  async function loadUsers(target) {
    showLoading(target, "Loading users…");
    try {
      const res = await listUsers();
      const users = (res && res.data) || [];
      clear(target);
      if (!users.length) {
        target.appendChild(el("div", { className: "empty" }, el("p", null, "No users yet.")));
        return;
      }
      target.appendChild(renderTable(users));
    } catch (err) {
      showError(target, err.message || "Failed to load users.", { onRetry: () => loadUsers(target) });
    }
  }

  function renderTable(users) {
    const table = el("table", { className: "table table--enterprise" });
    const head = document.createElement("thead");
    head.innerHTML =
      "<tr>" +
      "<th>Full name</th>" +
      "<th>Username</th>" +
      "<th>Email</th>" +
      "<th>Role</th>" +
      "<th>Company</th>" +
      "<th>Status</th>" +
      "<th>Last login</th>" +
      "<th class='table__actions'>Actions</th>" +
      "</tr>";
    table.appendChild(head);
    const tbody = document.createElement("tbody");
    for (const u of users) {
      const tr = document.createElement("tr");
      const role = (u.roles && u.roles[0]) || "viewer";
      const status = u.is_active ? "active" : "inactive";
      tr.appendChild(el("td", null,
        el("strong", null, escapeHtml(u.full_name || u.username)),
      ));
      tr.appendChild(el("td", { className: "mono" }, escapeHtml(u.username)));
      tr.appendChild(el("td", null, escapeHtml(u.email)));
      tr.appendChild(el("td", null, el("span", { className: `badge badge--role-${role}` }, roleLabel(role))));
      tr.appendChild(el("td", { className: "mono" }, String(u.company_id ?? "—")));
      tr.appendChild(el("td", null, el("span", { className: `badge badge--${status}` }, status === "active" ? "Active" : "Inactive")));
      tr.appendChild(el("td", null, formatDateTime(u.last_login_at)));

      const actions = el("td", { className: "table__actions" });
      actions.appendChild(el("button", { className: "btn btn-ghost btn-sm", onClick: () => openUserModal(u) }, "Edit"));
      if (u.is_active) {
        actions.appendChild(el("button", { className: "btn btn-ghost btn-sm", onClick: () => toggleActive(u, false) }, "Deactivate"));
      } else {
        actions.appendChild(el("button", { className: "btn btn-ghost btn-sm", onClick: () => toggleActive(u, true) }, "Activate"));
      }
      actions.appendChild(el("button", { className: "btn btn-ghost btn-sm", onClick: () => openPasswordModal(u) }, "Password"));
      actions.appendChild(el("button", { className: "btn btn-danger btn-sm", onClick: () => confirmDelete(u) }, "Delete"));
      tr.appendChild(actions);
      tbody.appendChild(tr);
    }
    table.appendChild(tbody);
    return el("div", { className: "card", style: "padding:0;" }, el("div", { className: "table-scroll" }, table));
  }

  async function toggleActive(u, activate) {
    try {
      await (activate ? activateUser(u.id) : deactivateUser(u.id));
      toast(activate ? `${u.username} activated` : `${u.username} deactivated`, { type: "success" });
      loadUsers(box);
    } catch (err) {
      toast(err.message || "Action failed", { type: "error" });
    }
  }

  function confirmDelete(u) {
    openModal({
      title: `Delete ${u.username}?`,
      body: el("p", null, `This permanently removes the account for ${escapeHtml(u.email)}. The company's data is not affected.`),
      actions: [
        { label: "Cancel", variant: "secondary", onClick: (m) => m.close() },
        {
          label: "Delete",
          variant: "danger",
          onClick: async (m) => {
            try {
              await deleteUser(u.id);
              m.close();
              toast(`Deleted ${u.username}`, { type: "success" });
              loadUsers(box);
            } catch (err) {
              toast(err.message || "Delete failed", { type: "error" });
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
        el("label", {}, "Username"),
        el("input", { type: "text", value: state.username, required: true, "data-field": "username" }),
      ),
      el("div", { className: "field" },
        el("label", {}, "Email"),
        el("input", { type: "email", value: state.email, required: true, "data-field": "email" }),
      ),
      el("div", { className: "field-row" },
        el("div", { className: "field", style: "flex:1;" },
          el("label", {}, "First name"),
          el("input", { type: "text", value: state.first_name, "data-field": "first_name" }),
        ),
        el("div", { className: "field", style: "flex:1;" },
          el("label", {}, "Last name"),
          el("input", { type: "text", value: state.last_name, "data-field": "last_name" }),
        ),
      ),
      el("div", { className: "field-row" },
        el("div", { className: "field", style: "flex:1;" },
          el("label", {}, "Role"),
          el("select", { "data-field": "role" }, ROLES.map((r) => el("option", { value: r, selected: r === state.role }, roleLabel(r)))),
        ),
        el("div", { className: "field", style: "flex:1;" },
          el("label", {}, "Company ID"),
          el("input", { type: "text", value: state.company_id, placeholder: "Required for non-admins", "data-field": "company_id" }),
        ),
      ),
      el("div", { className: "field-row" },
        el("div", { className: "field", style: "flex:1;" },
          el("label", {}, "Status"),
          el("select", { "data-field": "status" },
            el("option", { value: "active", selected: state.status === "active" }, "Active"),
            el("option", { value: "inactive", selected: state.status === "inactive" }, "Inactive"),
          ),
        ),
        !isEdit
          ? el("div", { className: "field", style: "flex:1;" },
            el("label", {}, "Password"),
            el("input", { type: "password", value: state.password, required: true, minlength: "6", "data-field": "password" }),
          )
          : el("div", { className: "field", style: "flex:1;" },
            el("label", {}, "Password"),
            el("input", { type: "password", value: state.password, disabled: true, placeholder: "Leave blank; use Password", "data-field": "password" }),
          ),
      ),
      errBox,
    );

    const m = openModal({
      title: isEdit ? `Edit ${user.username}` : "Add user",
      body: form,
      actions: [
        { label: "Cancel", variant: "secondary", onClick: (modal) => modal.close() },
        {
          label: isEdit ? "Save changes" : "Create user",
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
        errBox.appendChild(el("div", { className: "alert alert--error" }, "Enter a valid email address."));
        return;
      }
      if (payload.company_id === "" && payload.roles[0] !== "admin") {
        payload.company_id = null;
      }
      try {
        if (isEdit) {
          await updateUser(user.id, payload);
          toast("User updated", { type: "success" });
        } else {
          payload.password = form.querySelector('[data-field="password"]').value;
          await createUser(payload);
          toast("User created", { type: "success" });
        }
        modal.close();
        loadUsers(box);
      } catch (err) {
        errBox.appendChild(el("div", { className: "alert alert--error" }, escapeHtml(err.message || "Request failed.")));
      }
    }
  }

  function openPasswordModal(user) {
    const state = { password: "" };
    const errBox = el("div");
    const form = el("form", { onsubmit: (e) => { e.preventDefault(); submit(m); } },
      el("p", null, `Set a new password for ${escapeHtml(user.username)}.`),
      el("div", { className: "field" },
        el("label", {}, "New password"),
        el("input", { type: "password", value: state.password, required: true, minlength: "6", "data-field": "password" }),
      ),
      errBox,
    );

    const m = openModal({
      title: `Reset password · ${user.username}`,
      body: form,
      actions: [
        { label: "Cancel", variant: "secondary", onClick: (modal) => modal.close() },
        {
          label: "Reset password",
          variant: "primary",
          onClick: (modal) => submit(modal),
        },
      ],
    });

    async function submit(modal) {
      clear(errBox);
      const pw = form.querySelector('[data-field="password"]').value;
      if (!pw || pw.length < 6) {
        errBox.appendChild(el("div", { className: "alert alert--error" }, "Password must be at least 6 characters."));
        return;
      }
      try {
        await resetUserPassword(user.id, pw);
        modal.close();
        toast("Password reset", { type: "success" });
      } catch (err) {
        errBox.appendChild(el("div", { className: "alert alert--error" }, escapeHtml(err.message || "Reset failed.")));
      }
    }
  }
}