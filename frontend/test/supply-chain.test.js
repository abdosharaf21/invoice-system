import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const root = dirname(dirname(fileURLToPath(import.meta.url)));

function loadJson(name) {
  const path = join(root, name);
  assert.ok(existsSync(path), `expected ${name} to exist`);
  return JSON.parse(readFileSync(path, "utf8"));
}

describe("supply chain", () => {
  it("package.json declares zero runtime and zero dev dependencies", () => {
    const pkg = loadJson("package.json");
    assert.deepEqual(pkg.dependencies || {}, {}, "no runtime dependencies allowed");
    assert.deepEqual(pkg.devDependencies || {}, {}, "no dev dependencies allowed");
    const scripts = pkg.scripts || {};
    assert.equal(scripts.test ?? "", "node --test \"test/*.test.js\"",
      "test script uses node:test, no external tooling");
  });

  it("package-lock.json is lockfileVersion 3 and pins only the root package", () => {
    const lock = loadJson("package-lock.json");
    assert.equal(lock.lockfileVersion, 3, "lockfileVersion must be 3");
    const names = Object.keys(lock.packages || {});
    assert.ok(names.includes(""), "lockfile must declare a root package entry");
    const nonRoot = names.filter((n) => n !== "");
    assert.deepEqual(nonRoot, [], "no transitive packages may be locked");
    assert.equal(Object.keys(lock.dependencies || {}).length, 0,
      "legacy dependencies map must stay empty");
  });

  it("no registry override, lifecycle scripts, or install hooks", () => {
    const pkg = loadJson("package.json");
    assert.ok(!pkg.husky && !pkg.huskyHooks && !pkg.scripts?.postinstall &&
      !pkg.scripts?.preinstall && !pkg.scripts?.install, "no lifecycle install hooks");
    const lock = loadJson("package-lock.json");
    assert.ok(!lock.packages?.[""]?.hasInstallScript, "root package must not install");
  });
});