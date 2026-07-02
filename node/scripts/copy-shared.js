/**
 * Copy shared data directories into the node package directory so they are
 * included in the npm tarball.
 *
 * This runs as part of `npm run prepack`. What gets bundled:
 *
 *   templates/   mustache templates for charter, roster cards, CLAUDE.md, ...
 *   presets/     team-shape presets (fullstack-monorepo, data-pipeline, library)
 *   skills/      mustache skill templates rendered into .claude/skills/
 *   framework/   the config-driven runtime (install/ + assets/ + config/ +
 *                recipes/) that `2real-team init --with-hooks` bridges to via
 *                framework/install/bootstrap.py — the npm mirror of the Python
 *                package's hatch BundleSharedDataHook.
 *
 * To keep the tarball lean, development-only subtrees are excluded from the
 * copy: framework/tests/ (pytest suite, not needed at install time) and any
 * __pycache__/ or tool cache directories.
 */

import { cpSync, existsSync, mkdirSync } from "node:fs";
import { resolve, dirname, basename } from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const PKG_ROOT = resolve(__dirname, "..");
const REPO_ROOT = resolve(PKG_ROOT, "..");

const DIRS = ["templates", "presets", "skills", "framework"];

// Excluded anywhere in the copied trees (dev/test-only content).
const EXCLUDED_DIRS = new Set(["tests", "__pycache__", ".pytest_cache", ".ruff_cache"]);

/** cpSync filter: skip excluded directory subtrees and compiled bytecode. */
function includeInBundle(src) {
  const name = basename(src);
  if (EXCLUDED_DIRS.has(name)) return false;
  if (name.endsWith(".pyc")) return false;
  return true;
}

for (const dir of DIRS) {
  const src = resolve(REPO_ROOT, dir);
  const dest = resolve(PKG_ROOT, dir);

  if (!existsSync(src)) {
    console.warn(`Warning: source directory not found: ${src}`);
    continue;
  }

  if (existsSync(dest)) {
    // Already copied or symlinked — skip
    continue;
  }

  mkdirSync(dest, { recursive: true });
  cpSync(src, dest, { recursive: true, filter: includeInBundle });
  console.log(`Copied ${src} -> ${dest}`);
}
