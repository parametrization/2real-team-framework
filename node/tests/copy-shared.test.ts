/**
 * Tests for scripts/copy-shared.js — the prepack bundler that copies the shared
 * data trees (templates/, presets/, skills/, framework/) into the node package so
 * they ship in the npm tarball.
 *
 * Regression focus (issue #82): a real destination directory left over from an
 * earlier local `npm pack` is a STALE snapshot and must be refreshed on the next
 * prepack (framework/ changes every wave), NOT silently skipped. A *symlinked*
 * destination is a deliberate live-checkout escape hatch and must be preserved.
 *
 * Black-box: the real script is copied into a throwaway package layout and run
 * with `node`, so its `__dirname/../..` REPO_ROOT resolution is exercised for real.
 */

import { execFileSync } from "node:child_process";
import {
  cpSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  rmSync,
  symlinkSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

const __dirname = dirname(fileURLToPath(import.meta.url));
const REAL_SCRIPT = resolve(__dirname, "../scripts/copy-shared.js");
const SHARED_DIRS = ["templates", "presets", "skills", "framework"];

let root: string; // fake REPO_ROOT
let pkg: string; // fake PKG_ROOT (root/node)

/** Build a fake repo: <root>/{templates,presets,skills,framework} + <root>/node/scripts/copy-shared.js */
beforeEach(() => {
  root = mkdtempSync(resolve(tmpdir(), "copy-shared-"));
  pkg = resolve(root, "node");
  mkdirSync(resolve(pkg, "scripts"), { recursive: true });
  cpSync(REAL_SCRIPT, resolve(pkg, "scripts", "copy-shared.js"));
  // The real script is ESM and runs under node/package.json's "type":"module".
  // Reproduce that so the copy loads as ESM on every Node (18 has no syntax
  // auto-detection — without this it would parse as CommonJS and throw).
  writeFileSync(resolve(pkg, "package.json"), JSON.stringify({ type: "module" }) + "\n");
  for (const d of SHARED_DIRS) {
    mkdirSync(resolve(root, d), { recursive: true });
    writeFileSync(resolve(root, d, "marker.txt"), `${d}: v1\n`);
  }
});

afterEach(() => {
  rmSync(root, { recursive: true, force: true });
});

function runBundler(): string {
  return execFileSync("node", [resolve(pkg, "scripts", "copy-shared.js")], {
    encoding: "utf-8",
  });
}

function bundled(dir: string): string {
  return readFileSync(resolve(pkg, dir, "marker.txt"), "utf-8");
}

describe("copy-shared prepack bundler", () => {
  it("copies every shared dir into the package on a first pack", () => {
    runBundler();
    for (const d of SHARED_DIRS) expect(bundled(d)).toBe(`${d}: v1\n`);
  });

  it("refreshes a stale bundle instead of skipping it (issue #82)", () => {
    runBundler(); // first pack captures v1
    // Source moves forward a wave…
    for (const d of SHARED_DIRS) writeFileSync(resolve(root, d, "marker.txt"), `${d}: v2\n`);
    runBundler(); // second local pack
    for (const d of SHARED_DIRS) {
      expect(bundled(d)).toBe(`${d}: v2\n`); // NOT the stale v1
    }
  });

  it("drops bundled files no longer in source on refresh (full re-sync, no leftovers)", () => {
    runBundler();
    // A leftover in the BUNDLE that the source never had (e.g. a file removed
    // upstream between packs). rm+recopy must clear it.
    writeFileSync(resolve(pkg, "framework", "stale-only.txt"), "leftover from an old pack\n");
    runBundler();
    expect(() => readFileSync(resolve(pkg, "framework", "stale-only.txt"), "utf-8")).toThrow();
  });

  it("preserves a symlinked destination (live-checkout escape hatch)", () => {
    // Developer symlinks node/framework -> ../framework for live dev.
    symlinkSync(resolve(root, "framework"), resolve(pkg, "framework"), "dir");
    writeFileSync(resolve(root, "framework", "marker.txt"), "framework: live\n");
    const out = runBundler();
    // The symlink is left in place (reads straight through to the live source)…
    expect(bundled("framework")).toBe("framework: live\n");
    expect(out).toMatch(/symlink/i);
    // …and the source tree was not clobbered by a copy-onto-itself.
    expect(readFileSync(resolve(root, "framework", "marker.txt"), "utf-8")).toBe(
      "framework: live\n",
    );
  });

  it("excludes tests/ and __pycache__ subtrees from the bundle", () => {
    mkdirSync(resolve(root, "framework", "tests"), { recursive: true });
    writeFileSync(resolve(root, "framework", "tests", "test_x.py"), "x\n");
    mkdirSync(resolve(root, "framework", "__pycache__"), { recursive: true });
    writeFileSync(resolve(root, "framework", "__pycache__", "x.pyc"), "bytecode\n");
    runBundler();
    expect(() =>
      readFileSync(resolve(pkg, "framework", "tests", "test_x.py"), "utf-8"),
    ).toThrow();
    expect(() =>
      readFileSync(resolve(pkg, "framework", "__pycache__", "x.pyc"), "utf-8"),
    ).toThrow();
  });
});
