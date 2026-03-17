/**
 * Copy shared data directories (templates, presets, skills) into the node
 * package directory so they are included in the npm tarball.
 *
 * This runs as part of `npm run prepack`.
 */

import { cpSync, existsSync, mkdirSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const PKG_ROOT = resolve(__dirname, "..");
const REPO_ROOT = resolve(PKG_ROOT, "..");

const DIRS = ["templates", "presets", "skills"];

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
  cpSync(src, dest, { recursive: true });
  console.log(`Copied ${src} -> ${dest}`);
}
