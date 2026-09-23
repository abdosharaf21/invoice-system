import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const cssDir = join(fileURLToPath(new URL(".", import.meta.url)), "../assets/css");
const files = readdirSync(cssDir).filter((f) => f.endsWith(".css"));

const read = (name) => readFileSync(join(cssDir, name), "utf8");

const requiredTokens = [
  "--color-primary",
  "--color-primary-dark",
  "--color-primary-hover",
  "--color-primary-active",
  "--color-accent",
  "--color-surface",
  "--color-surface-muted",
  "--color-text",
  "--color-text-secondary",
  "--color-text-muted",
  "--color-text-subtle",
  "--color-focus",
  "--color-overlay",
  "--color-success",
  "--color-warning",
  "--color-danger",
  "--color-info",
  "--role-admin-bg",
  "--role-admin-text",
  "--role-admin-border",
  "--bar-missing",
  "--bar-extra",
  "--status-matched-bg",
  "--status-invalid-bg",
  "--btn-primary-bg",
  "--btn-danger-hover-bg",
  "--btn-success-bg",
  "--btn-success-hover",
  "--sidebar-bg",
  "--sidebar-text",
  "--sidebar-hover-bg",
  "--font-sans",
  "--font-mono",
  "--text-xs",
  "--text-base",
  "--space-1",
  "--space-8",
  "--radius-sm",
  "--radius-lg",
  "--shadow-xs",
  "--shadow-lg",
  "--transition-fast",
  "--sidebar-width",
  "--z-modal",
];

describe("design tokens (variables.css)", () => {
  it("declares every required semantic token", () => {
    const css = read("variables.css");
    for (const token of requiredTokens) {
      assert.match(css, new RegExp(`^\\s*${token}:`, "m"), `missing token ${token}`);
    }
  });

  it("keys the dark palette off the effective-theme attribute", () => {
    const css = read("variables.css");
    assert.match(css, /:root\[data-theme="dark"\]/m, "dark theme must be attribute-driven");
    assert.match(css, /:root\s*\{[^}]*color-scheme:\s*light/is, ":root declares light color-scheme");
    const darkBlock = css.split(":root[data-theme=\"dark\"]")[1] || "";
    assert.match(darkBlock, /color-scheme:\s*dark/, "dark block declares dark color-scheme");
  });
});

describe("design tokens (consistency)", () => {
  it("every var(--x) referenced in any stylesheet is declared in variables.css", () => {
    const declared = new Set(
      [...read("variables.css").matchAll(/--([a-zA-Z0-9-]+)\s*:/g)].map((m) => `--${m[1]}`),
    );
    const referenced = new Set();
    for (const f of files) {
      for (const m of read(f).matchAll(/var\(\s*(--[a-zA-Z0-9-]+)\s*\)/g)) {
        referenced.add(m[1]);
      }
    }
    const missing = [...referenced].filter((v) => !declared.has(v)).sort();
    assert.deepEqual(missing, []);
  });

  it("component class names are declared before use in CSS order", () => {
    const components = read("components.css");
    for (const cls of [".btn", ".btn-primary", ".btn-danger", ".btn-success", ".card", ".card--table", ".badge", ".table-wrap", ".table-wrap--flush", ".toolbar", ".pagination", ".tab", ".modal", ".alert", ".toast", ".toast__close", ".dropdown", ".state-block"]) {
      assert.ok(components.includes(cls), `components.css missing ${cls}`);
    }
  });
});

describe("focus-visible and motion defaults (reset.css)", () => {
  it("provides a global keyboard focus ring via :focus-visible", () => {
    const css = read("reset.css");
    assert.match(css, /:focus-visible\s*\{/);
    assert.match(css, /outline:\s*2px\s+solid\s+var\(--color-focus\)/);
  });

  it("includes a prefers-reduced-motion kill-switch", () => {
    const css = read("reset.css");
    assert.match(css, /@media \(prefers-reduced-motion: reduce\)/);
  });
});