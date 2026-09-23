import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(fileURLToPath(new URL(".", import.meta.url)), "../assets");

function walk(dir, out = []) {
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) {
      walk(full, out);
    } else if (/\.(css|js)$/.test(entry)) {
      out.push(full);
    }
  }
  return out;
}

describe("RTL foundation guard", () => {
  it("no physical margin/padding left-right anywhere in CSS or JS", () => {
    const offenders = [];
    for (const file of walk(root)) {
      const text = readFileSync(file, "utf8");
      for (const name of ["margin-left", "margin-right", "padding-left", "padding-right"]) {
        for (const line of text.split("\n")) {
          if (line.includes(name)) {
            offenders.push(`${relative(root, file)}: ${line.trim()}`);
          }
        }
      }
    }
    assert.deepEqual(offenders, []);
  });

  it("inline style strings in JS use logical properties", () => {
    const offenders = [];
    for (const file of walk(join(root, "js"))) {
      const text = readFileSync(file, "utf8");
      for (const m of text.matchAll(/style:\s*"([^"]*)"/g)) {
        if (/(?:margin|padding)-(?:left|right)\s*[:;]/.test(m[1])) {
          offenders.push(`${relative(root, file)}: ${m[0]}`);
        }
      }
    }
    assert.deepEqual(offenders, []);
  });

  it("app shell media query provides an explicit [dir=rtl] sidebar flip", () => {
    const css = readFileSync(join(root, "css/layout.css"), "utf8");
    assert.match(css, /\[dir="rtl"\]\s*\.sidebar/);
  });
});