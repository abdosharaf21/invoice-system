import { describe, it, beforeEach } from "node:test";
import assert from "node:assert/strict";
import "./helpers/dom.js";
import { authStore, getCurrentRole, hasRole, canReconcile, isAdmin } from "../assets/js/auth/store.js";

describe("auth store", () => {
  beforeEach(() => {
    authStore.clear();
  });

  it("persists tokens and reports authentication", () => {
    assert.equal(authStore.isAuthenticated(), false);
    authStore.setTokens({ access: "a", refresh: "r" });
    assert.equal(authStore.isAuthenticated(), true);
    assert.deepEqual(authStore.getTokens(), { access: "a", refresh: "r" });
  });

  it("clears everything on logout", () => {
    authStore.setTokens({ access: "a", refresh: "r" });
    authStore.setUser({ id: 1, roles: ["admin"] });
    authStore.clear();
    assert.equal(authStore.isAuthenticated(), false);
    assert.equal(authStore.getUser(), null);
  });

  it("caches the user payload", () => {
    authStore.setUser({ id: 7, username: "sam", roles: ["accountant"] });
    assert.equal(authStore.getUser().id, 7);
    authStore.setUser(null);
    assert.equal(authStore.getUser(), null);
  });

  describe("role helpers", () => {
    it("reads the primary role", () => {
      authStore.setUser({ roles: ["manager"] });
      assert.equal(getCurrentRole(), "manager");
      assert.equal(hasRole("manager"), true);
      assert.equal(hasRole("admin"), false);
    });
    it("is reconcilable for admin/accountant/manager only", () => {
      for (const role of ["admin", "accountant", "manager"]) {
        authStore.setUser({ roles: [role] });
        assert.equal(canReconcile(), true, role);
      }
      authStore.setUser({ roles: ["viewer"] });
      assert.equal(canReconcile(), false);
    });
    it("is admin-only for user administration", () => {
      authStore.setUser({ roles: ["admin"] });
      assert.equal(isAdmin(), true);
      authStore.setUser({ roles: ["manager"] });
      assert.equal(isAdmin(), false);
    });
    it("returns null role without a user", () => {
      assert.equal(getCurrentRole(), null);
      assert.equal(canReconcile(), false);
    });
  });
});