/**
 * Read the CLI version from the package's own package.json (single source of
 * truth — no hardcoded version strings in code). Works from both `src/` (dev,
 * via vitest/tsx) and `dist/` (built package): each is one level below the
 * package root.
 */

import { readFileSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));

export function readPackageVersion(): string {
  const pkgPath = resolve(__dirname, "..", "package.json");
  const pkg = JSON.parse(readFileSync(pkgPath, "utf-8")) as { version?: string };
  if (!pkg.version) {
    throw new Error(`package.json at ${pkgPath} has no version field`);
  }
  return pkg.version;
}
