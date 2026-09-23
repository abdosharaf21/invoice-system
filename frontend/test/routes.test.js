import { describe, it, beforeEach } from "node:test";
import assert from "node:assert/strict";
import "./helpers/dom.js";
import { authStore } from "../assets/js/auth/store.js";
import { resolveRoute, canEnter, canSeeSection } from "../assets/js/config/routes.js";

describe("route resolution", () => {
  beforeEach(() => {
    authStore.clear();
  });

  it("resolves static routes", () => {
    const dash = resolveRoute("#/dashboard");
    assert.equal(dash.route.path, "dashboard");
    const login = resolveRoute("");
    assert.equal(login.route.path, "login");
  });

  it("resolves parametric routes and captures params", () => {
    const run = resolveRoute("#/reconciliation/42");
    assert.equal(run.route.path, "reconciliation/:id");
    assert.deepEqual(run.params, ["42"]);

    const imp = resolveRoute("#/IMPORTS/7");
    assert.equal(imp.route.path, "imports/:id");
    assert.deepEqual(imp.params, ["7"]);
  });

  it("returns null for unknown routes", () => {
    assert.equal(resolveRoute("#/definitely-not-a-page"), null);
  });
});

describe("role gating", () => {
  beforeEach(() => {
    authStore.clear();
  });

  const runRoute = (hash) => resolveRoute(hash).route;

  it("allows operators into imports/reconciliation/reports", () => {
    for (const role of ["admin", "accountant", "manager"]) {
      authStore.setUser({ roles: [role] });
      assert.equal(canEnter(runRoute("#/imports")), true, role);
      assert.equal(canEnter(runRoute("#/reconciliation/1")), true, role);
      assert.equal(canEnter(runRoute("#/reports")), true, role);
    }
  });

  it("denies viewers into imports/reconciliation/reports but allows read-only pages", () => {
    authStore.setUser({ roles: ["viewer"] });
    assert.equal(canEnter(runRoute("#/imports")), false);
    assert.equal(canEnter(runRoute("#/reconciliation/1")), false);
    assert.equal(canEnter(runRoute("#/reports")), false);
    assert.equal(canEnter(runRoute("#/dashboard")), true);
    assert.equal(canEnter(runRoute("#/account")), true);
  });

  it("restricts user administration to admins", () => {
    authStore.setUser({ roles: ["admin"] });
    assert.equal(canEnter(runRoute("#/users")), true);

    authStore.setUser({ roles: ["manager"] });
    assert.equal(canEnter(runRoute("#/users")), false);
  });

  it("filters nav sections by role", () => {
    authStore.setUser({ roles: ["viewer"] });
    assert.equal(canSeeSection({ title: "Operations", minRoles: ["admin", "accountant", "manager"] }), false);
    assert.equal(canSeeSection({ title: "Overview" }), true);
    authStore.setUser({ roles: ["admin"] });
    assert.equal(canSeeSection({ title: "Administration", minRoles: ["admin"] }), true);
  });

  it("shows the monitoring section to admins and managers only", () => {
    authStore.setUser({ roles: ["admin"] });
    assert.equal(canSeeSection({ title: "Monitoring", minRoles: ["admin", "manager"] }), true);
    authStore.setUser({ roles: ["manager"] });
    assert.equal(canSeeSection({ title: "Monitoring", minRoles: ["admin", "manager"] }), true);
    authStore.setUser({ roles: ["accountant"] });
    assert.equal(canSeeSection({ title: "Monitoring", minRoles: ["admin", "manager"] }), false);
    authStore.setUser({ roles: ["viewer"] });
    assert.equal(canSeeSection({ title: "Monitoring", minRoles: ["admin", "manager"] }), false);
  });
});