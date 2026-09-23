/**
 * Dashboard localization regression tests.
 *
 * Guards the phase-6 dashboard against hardcoded English labels: every
 * user-visible string must resolve through the active i18n dictionary, so the
 * dashboard re-renders in Arabic (RTL) when the locale switches.
 */

import { describe, it, beforeEach } from "node:test";
import assert from "node:assert/strict";
import "./helpers/dom.js";
import { t, setLocale, getLocale } from "../assets/js/i18n/index.js";
import { authStore } from "../assets/js/auth/store.js";
import { renderDashboard } from "../assets/js/pages/dashboard.js";

const RUNS = {
  runs: [
    {
      id: 9,
      period: "2024-03",
      status: "completed",
      matched_count: 12,
      unmatched_count: 3,
      error_count: 1,
      invoice_count: 15,
      tax_invoice_count: 14,
      started_at: "2024-04-01T09:30:00Z",
    },
    {
      id: 8,
      period: "2024-02",
      status: "failed",
      matched_count: 5,
      unmatched_count: 2,
      error_count: 4,
      invoice_count: 9,
      tax_invoice_count: 7,
      started_at: "2024-03-01T09:30:00Z",
    },
  ],
};

const SUMMARY = {
  summary: {
    total_results: 20,
    matched: 12,
    mismatched: 1,
    missing_in_tax_authority: 1,
    extra_in_tax_authority: 1,
    invalid: 0,
  },
};

/** Collect all rendered text in document order (deep). */
function textOf(node) {
  let out = "";
  for (const child of node.childNodes || []) {
    if (child.nodeType === 3) out += child.textContent || "";
    else out += textOf(child);
  }
  return out;
}

function envelope(data) {
  return {
    ok: true,
    status: 200,
    headers: new Map([["content-type", "application/json"]]),
    async json() { return { success: true, data }; },
  };
}

function stubApi() {
  const original = globalThis.fetch;
  globalThis.fetch = async (url) => {
    const path = String(url);
    return envelope(path.includes("/summary") ? SUMMARY : RUNS);
  };
  return () => { globalThis.fetch = original; };
}

describe("dashboard localization", () => {
  beforeEach(() => {
    authStore.setTokens({ access: "test-token", refresh: "test-refresh" });
    authStore.setUser({ full_name: "Ahmed", roles: ["admin"] });
    setLocale("en");
  });

  it("renders Arabic labels when the locale is ar", async () => {
    const restore = stubApi();
    try {
      setLocale("ar");
      assert.equal(getLocale(), "ar");
      const container = document.createElement("div");
      await renderDashboard(container);
      const text = textOf(container);

      for (const arabic of [
        t("dash.welcome", { name: "Ahmed" }),
        t("dash.kpiRuns"),
        t("dash.kpiMatched"),
        t("dash.kpiUnmatched"),
        t("dash.kpiErrors"),
        t("dash.recent"),
        t("dash.thPeriod"),
        t("dash.thStatus"),
        t("dash.thMatched"),
        t("dash.thStarted"),
        t("status.completed"),
        t("status.failed"),
        t("status.matched"),
      ]) {
        assert.ok(text.includes(arabic), `expected Arabic string missing: ${arabic}`);
      }

      assert.ok(!text.includes("Reconciliation runs"), "English 'Reconciliation runs' leaked through");
      assert.ok(!text.includes("Matched"), "English 'Matched' leaked through");
      assert.ok(!text.includes("Period"), "English 'Period' leaked through");
      assert.ok(!text.includes("Recent reconciliation activity"), "English 'Recent reconciliation activity' leaked through");
    } finally {
      restore();
    }
  });

  it("re-renders into the new language when the locale switches", async () => {
    const restore = stubApi();
    try {
      const container = document.createElement("div");
      setLocale("en");
      await renderDashboard(container);
      const enText = textOf(container);
      assert.ok(enText.includes("Reconciliation runs"), "English dashboard did not render under 'en' locale");
      assert.ok(!enText.includes("جولات المطابقة"), "Arabic leaked into the English dashboard");

      setLocale("ar");
      await renderDashboard(container);
      const arText = textOf(container);
      assert.ok(arText.includes(t("dash.kpiRuns")));
      assert.ok(arText.includes("جولات المطابقة"));
      assert.ok(arText.includes(t("dash.welcome", { name: "Ahmed" })));
      assert.ok(!arText.includes("Welcome, Ahmed"), "English dashboard greeting survived the locale switch");
    } finally {
      restore();
    }
  });

  it("translates run status badges through the i18n dictionary", async () => {
    const restore = stubApi();
    try {
      const onlyCompleted = {
        runs: [RUNS.runs[0]],
      };
      const original = globalThis.fetch;
      globalThis.fetch = async (url) => {
        const path = String(url);
        return envelope(path.includes("/summary") ? SUMMARY : onlyCompleted);
      };
      setLocale("ar");
      const container = document.createElement("div");
      await renderDashboard(container);
      const text = textOf(container);
      assert.ok(text.includes(t("status.completed")), "Arabic 'completed' badge missing");
      assert.ok(!text.includes("Completed"), "English 'Completed' badge leaked through");
      globalThis.fetch = original;
    } finally {
      restore();
    }
  });
});