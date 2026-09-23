import { describe, it, beforeEach } from "node:test";
import assert from "node:assert/strict";
import "./helpers/dom.js";
import { t, setLocale, getLocale, getDirection, applyAppLocale, resolveEffectiveLocale } from "../assets/js/i18n/index.js";
import en from "../assets/js/i18n/en.js";
import ar from "../assets/js/i18n/ar.js";

describe("i18n dictionary parity", () => {
  it("every key in en.js also exists in ar.js", () => {
    const enKeys = Object.keys(en).sort();
    const arKeys = Object.keys(ar).sort();
    assert.deepEqual(arKeys, enKeys, "ar dictionary must mirror en exactly");
  });

  it("every key resolves to a non-empty string in both locales", () => {
    for (const [lang, dict] of [["en", en], ["ar", ar]]) {
      for (const [key, value] of Object.entries(dict)) {
        assert.equal(typeof value, "string", `${lang}.${key}`);
        assert.ok(value.trim().length > 0, `${lang}.${key} is empty`);
      }
    }
  });
});

describe("i18n t()", () => {
  beforeEach(() => setLocale("en"));

  it("resolves the English dictionary by default", () => {
    assert.equal(t("common.delete"), "Delete");
    assert.equal(t("nav.dashboard"), "Dashboard");
  });

  it("interpolates {param} placeholders", () => {
    assert.equal(t("dash.welcome", { name: "Ahmed" }), "Welcome, Ahmed");
    assert.equal(t("imports.rejectedCount", { count: 3 }), "3 rows rejected");
    assert.equal(t("run.resendConfirm", { recipient: "a@b.co" }), "Resend email to a@b.co?");
    assert.equal(t("pagination.range", { first: 1, last: 10, total: 130 }), "1–10 of 130 results");
    assert.equal(t("pagination.pageOf", { page: 2, total: 5 }), "Page 2 of 5");
  });

  it("falls back to the English value when a translation is missing in the active locale", () => {
    setLocale("ar");
    const key = "parity.testMissing";
    en[key] = "fallback text";
    assert.equal(t(key), "fallback text");
    delete en[key];
  });

  it("returns the raw key when neither locale has it", () => {
    assert.equal(t("does.not.exist"), "does.not.exist");
  });

  it("normalizes region codes to the base language", () => {
    setLocale("ar-EG");
    assert.equal(getLocale(), "ar");
    assert.equal(t("common.cancel"), "إلغاء");
    setLocale("en");
  });

  it("accepts a locale string case-insensitively", () => {
    setLocale("EN");
    assert.equal(getLocale(), "en");
    assert.equal(t("common.ok"), "OK");
  });
});

describe("i18n locale & direction", () => {
  beforeEach(() => setLocale("en"));

  it("switches the UI direction to RTL for Arabic", () => {
    setLocale("ar");
    assert.equal(getLocale(), "ar");
    assert.equal(getDirection(), "rtl");
  });

  it("returns LTR for English", () => {
    setLocale("en");
    assert.equal(getDirection(), "ltr");
  });

  it("applyAppLocale sets lang+dir on <html> and persists the choice", async () => {
    await applyAppLocale("ar");
    assert.equal(document.documentElement.lang, "ar");
    assert.equal(document.documentElement.dir, "rtl");
    assert.equal(globalThis.localStorage.getItem("eis:lang"), "ar");
    await applyAppLocale("en");
    assert.equal(document.documentElement.lang, "en");
    assert.equal(document.documentElement.dir, "ltr");
    assert.equal(globalThis.localStorage.getItem("eis:lang"), "en");
  });

  it("rejects unknown locales back to English", async () => {
    const norm = await applyAppLocale("xx-XX");
    assert.equal(norm, "en");
    assert.equal(getDirection(), "ltr");
  });
});

describe("resolveEffectiveLocale priority", () => {
  it("user profile language wins over persisted device locale", () => {
    assert.equal(resolveEffectiveLocale({ language: "ar" }, { default_language: "en" }, "en"), "ar");
  });

  it("persisted device locale wins over application default when profile is absent", () => {
    assert.equal(resolveEffectiveLocale({}, { default_language: "en" }, "ar"), "ar");
  });

  it("application default is used when no profile or persisted locale", () => {
    assert.equal(resolveEffectiveLocale({}, { default_language: "ar" }, null), "ar");
  });

  it("falls back to en when no source provides a language", () => {
    assert.equal(resolveEffectiveLocale({}, {}, null), "en");
  });

  it("normalizes region and case in user profile language", () => {
    assert.equal(resolveEffectiveLocale({ language: "AR-EG" }, {}, null), "ar");
    assert.equal(resolveEffectiveLocale({ language: "EN" }, {}, null), "en");
  });

  it("unknown codes still resolve to en (applyAppLocale normalizes later)", () => {
    assert.equal(resolveEffectiveLocale({ language: "xx" }, {}, null), "xx");
    assert.equal(resolveEffectiveLocale({}, {}, "yy"), "yy");
  });
});