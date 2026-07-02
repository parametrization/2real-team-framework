/**
 * Bridge: install the config-driven framework runtime (hooks/lib/skills/config).
 *
 * Node twin of the Python package's `real_team/framework_install.py`. The
 * mustache layer (`bootstrap.ts`) scaffolds the *team* (charter, roster cards,
 * trust matrix). This module installs the *runtime* — the genericised hooks,
 * libs, the lifecycle state machine, the `wave-lifecycle` skill,
 * `framework.config.json`, and the dispatcher wiring in `settings.json` — by
 * invoking the framework's own deterministic installer
 * (`framework/install/bootstrap.py`) against the same target. That keeps a
 * single source of truth for the install logic (no duplicated copy/merge code)
 * and lets `2real-team init` lay down a complete, runnable `.claude/` instead
 * of templates alone.
 *
 * The framework assets are bundled into the npm tarball under `framework/`
 * (see `scripts/copy-shared.js`); in a source checkout they resolve to the
 * repo-root `framework/`. The installer itself is Python, so the bridge needs
 * a Python 3 interpreter on PATH (`python3`, falling back to `python`). When
 * either the assets or the interpreter are missing the bridge degrades
 * gracefully (returns a typed non-`ran` result) so `init` still completes its
 * team scaffolding.
 *
 * `--no-team` is always passed: the CLI already wrote its own roster cards, so
 * the framework installer lays down only hooks/lib/skills/config.
 */

import { spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import { resolve, join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));

/**
 * Minimal shape of the `spawnSync` result the bridge consumes. Kept structural
 * so tests can inject a fake runner and assert the exact argv.
 */
export interface SpawnResult {
  status: number | null;
  stdout?: string | Buffer | null;
  stderr?: string | Buffer | null;
  error?: Error;
}

export type SpawnRunner = (
  command: string,
  args: string[],
  options: Record<string, unknown>,
) => SpawnResult;

const defaultRunner: SpawnRunner = (command, args, options) =>
  spawnSync(command, args, options) as SpawnResult;

/**
 * Locate the framework root (the dir holding `install/` + `assets/`).
 *
 * Prefers the tarball-bundled copy (`dist/ -> ../framework`); falls back to
 * the repo-checkout layout (`node/src|dist -> ../../framework`). Returns null
 * when neither has a runnable `install/bootstrap.py`.
 */
export function resolveFrameworkRoot(): string | null {
  const candidates = [
    resolve(__dirname, "..", "framework"),
    resolve(__dirname, "../..", "framework"),
  ];
  for (const root of candidates) {
    if (existsSync(join(root, "install", "bootstrap.py"))) return root;
  }
  return null;
}

/**
 * Find a Python 3 interpreter on PATH. Tries `python3` first, then `python`.
 * Returns the command name, or null when neither runs.
 */
export function findPython(runner: SpawnRunner = defaultRunner): string | null {
  for (const cmd of ["python3", "python"]) {
    const res = runner(cmd, ["--version"], { stdio: "ignore" });
    if (!res.error && res.status === 0) return cmd;
  }
  return null;
}

export interface FrameworkInstallOptions {
  /** scm.owner (GitHub org/user) forwarded as `--owner`. */
  owner?: string | null;
  /** Hook shell; the bootstrapper default. Always forwarded. */
  shell?: string;
  /** Merge model forwarded as `--merge-model`. */
  mergeModel?: string | null;
  /**
   * Unified YAML install config, forwarded as `--install-config` so the
   * bootstrapper resolves every install-time decision (ontology, pre_push,
   * children, …) from the same file the CLI read.
   */
  installConfig?: string | null;
  /**
   * Tri-state: `true` passes `--with-ontology`, `false` passes
   * `--no-ontology`, and `undefined` (default) passes neither so the
   * bootstrapper resolves `ontology.enabled` from the install config
   * (flags > user YAML > shipped default ON). This keeps a CLI default from
   * silently overriding a forwarded YAML.
   */
  withOntology?: boolean;
  dryRun?: boolean;
}

export type FrameworkInstallResult =
  | { kind: "ran"; status: number; stdout: string; stderr: string; argv: string[] }
  | { kind: "no-framework" }
  | { kind: "no-python" };

/**
 * Build the exact argv used to subprocess the framework bootstrapper. The
 * subprocess always runs `--no-team --non-interactive` — it can never prompt.
 */
export function buildBootstrapArgv(
  python: string,
  frameworkRoot: string,
  target: string,
  opts: FrameworkInstallOptions = {},
): string[] {
  const argv = [
    python,
    join(frameworkRoot, "install", "bootstrap.py"),
    target,
    "--no-team",
    "--non-interactive",
    "--shell",
    opts.shell ?? "bash",
  ];
  if (opts.installConfig) argv.push("--install-config", String(opts.installConfig));
  if (opts.owner) argv.push("--owner", opts.owner);
  if (opts.mergeModel) argv.push("--merge-model", opts.mergeModel);
  if (opts.withOntology === true) argv.push("--with-ontology");
  else if (opts.withOntology === false) argv.push("--no-ontology");
  if (opts.dryRun) argv.push("--dry-run");
  return argv;
}

/**
 * Install the framework runtime into `target` via its own bootstrapper.
 *
 * Degrades gracefully: `{ kind: "no-framework" }` when the bundled assets are
 * missing, `{ kind: "no-python" }` when no Python 3 interpreter is on PATH.
 * Callers should report a soft notice for either, not fail — the team
 * scaffolding is already in place.
 */
export function installFramework(
  target: string,
  opts: FrameworkInstallOptions = {},
  runner: SpawnRunner = defaultRunner,
): FrameworkInstallResult {
  const root = resolveFrameworkRoot();
  if (root === null) return { kind: "no-framework" };

  const python = findPython(runner);
  if (python === null) return { kind: "no-python" };

  const argv = buildBootstrapArgv(python, root, target, opts);
  const res = runner(argv[0], argv.slice(1), { encoding: "utf-8" });
  return {
    kind: "ran",
    status: res.status ?? 1,
    stdout: String(res.stdout ?? ""),
    stderr: String(res.stderr ?? ""),
    argv,
  };
}

/**
 * Human-readable outcome message for a bridge result, including the
 * degradation guidance when the Python runtime is unavailable.
 */
export function describeInstallResult(result: FrameworkInstallResult): string {
  switch (result.kind) {
    case "no-framework":
      return (
        "Framework runtime not installed: bundled assets not found " +
        "(re-run from a source checkout, or use the standalone framework installer)."
      );
    case "no-python":
      return (
        "Framework runtime not installed: no Python 3 interpreter found on PATH.\n" +
        "The team scaffolding (charter, roster, skills) was still created, but the\n" +
        "hooks/lib/lifecycle runtime was skipped — it is installed by a Python\n" +
        "bootstrapper bundled with this package. To finish the install either:\n" +
        "  - install python3 (https://www.python.org/downloads/) and re-run\n" +
        "    `2real-team init --with-hooks`, or\n" +
        "  - use the Python package instead: `pip install 2real-team-framework`."
      );
    case "ran":
      if (result.status !== 0) {
        const detail = (result.stderr || result.stdout).trim().slice(0, 500);
        return `Framework runtime install reported an issue (exit ${result.status}):\n${detail}`;
      }
      return "Installed the framework runtime (hooks/lib/skills/config).";
  }
}
