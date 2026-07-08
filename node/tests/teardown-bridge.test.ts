/**
 * Tests for the Node -> Python teardown/restore bridge: exact argv mapping for
 * `uninstall`/`restore`, safety-flag pass-through (`--dry-run` /
 * `--non-interactive`), the spawn-runner wiring (injected fake — no real
 * process is spawned), degradation results, and the degradation messages.
 *
 * These are the parity guards for #280: they go red if the bridge stops
 * forwarding a safety flag, targets the wrong command script, or fails to
 * degrade when the runtime is unavailable.
 */

import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { join, resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

import {
  buildTeardownArgv,
  runTeardown,
  uninstallFramework,
  restoreFramework,
  describeTeardownDegradation,
  resolveFrameworkRoot,
  type SpawnRunner,
  type SpawnResult,
  type TeardownCommand,
} from "../src/framework-install.js";

interface Call {
  cmd: string;
  args: string[];
}

/** Runner that answers python `--version` probes and the teardown call. */
function makeRunner(
  calls: Call[],
  pythonResults: Record<string, SpawnResult>,
  teardownResult: SpawnResult = { status: 0, stdout: "", stderr: "" },
): SpawnRunner {
  return (cmd, args) => {
    calls.push({ cmd, args });
    if (args.length === 1 && args[0] === "--version") {
      return pythonResults[cmd] ?? { status: null, error: new Error(`ENOENT: ${cmd}`) };
    }
    return teardownResult;
  };
}

const PYTHON3_OK: Record<string, SpawnResult> = { python3: { status: 0 } };

describe("buildTeardownArgv — exact flag mapping", () => {
  it("maps uninstall to uninstall.py with no flags by default", () => {
    const argv = buildTeardownArgv("python3", "/fw", "uninstall", "/target");
    expect(argv).toEqual(["python3", join("/fw", "install", "uninstall.py"), "/target"]);
  });

  it("maps restore to restore.py", () => {
    const argv = buildTeardownArgv("python3", "/fw", "restore", "/target");
    expect(argv[1]).toBe(join("/fw", "install", "restore.py"));
  });

  it("forwards --non-interactive then --dry-run in that order", () => {
    const argv = buildTeardownArgv("python3", "/fw", "uninstall", "/t", {
      nonInteractive: true,
      dryRun: true,
    });
    expect(argv).toEqual([
      "python3",
      join("/fw", "install", "uninstall.py"),
      "/t",
      "--non-interactive",
      "--dry-run",
    ]);
  });

  it("forwards only --dry-run when non-interactive is unset (consent gate preserved)", () => {
    const argv = buildTeardownArgv("python3", "/fw", "restore", "/t", { dryRun: true });
    expect(argv).toContain("--dry-run");
    expect(argv).not.toContain("--non-interactive");
  });

  it("forwards only --non-interactive when dry-run is unset", () => {
    const argv = buildTeardownArgv("python3", "/fw", "uninstall", "/t", {
      nonInteractive: true,
    });
    expect(argv).toContain("--non-interactive");
    expect(argv).not.toContain("--dry-run");
  });
});

describe("runTeardown — spawn wiring + degradation", () => {
  const cmds: TeardownCommand[] = ["uninstall", "restore"];

  for (const command of cmds) {
    it(`subprocesses the bundled ${command}.py with the mapped argv`, () => {
      const calls: Call[] = [];
      const runner = makeRunner(calls, PYTHON3_OK, { status: 0, stdout: "ok", stderr: "" });
      const result = runTeardown(command, "/target", { nonInteractive: true }, runner);

      expect(result.kind).toBe("ran");
      if (result.kind !== "ran") return;
      const root = resolveFrameworkRoot()!;
      expect(result.argv).toEqual([
        "python3",
        join(root, "install", `${command}.py`),
        "/target",
        "--non-interactive",
      ]);
      // Last spawn is the teardown subprocess itself, with the same argv.
      const last = calls[calls.length - 1];
      expect([last.cmd, ...last.args]).toEqual(result.argv);
    });
  }

  it("passes --dry-run through to the subprocess", () => {
    const calls: Call[] = [];
    const runner = makeRunner(calls, PYTHON3_OK);
    runTeardown("restore", "/target", { dryRun: true }, runner);
    const last = calls[calls.length - 1];
    expect(last.args).toContain("--dry-run");
  });

  it("does NOT pass --non-interactive when unset (subprocess keeps its consent gate)", () => {
    const calls: Call[] = [];
    const runner = makeRunner(calls, PYTHON3_OK);
    runTeardown("uninstall", "/target", {}, runner);
    const last = calls[calls.length - 1];
    expect(last.args).not.toContain("--non-interactive");
  });

  it("degrades to no-python without invoking the teardown subprocess", () => {
    const calls: Call[] = [];
    const runner = makeRunner(calls, {});
    const result = runTeardown("uninstall", "/target", { nonInteractive: true }, runner);
    expect(result).toEqual({ kind: "no-python" });
    // Only the two interpreter probes — never the teardown subprocess.
    expect(calls.map((c) => c.cmd)).toEqual(["python3", "python"]);
  });

  it("surfaces a nonzero teardown exit with stderr", () => {
    const runner = makeRunner([], PYTHON3_OK, { status: 5, stdout: "", stderr: "boom" });
    const result = runTeardown("restore", "/target", { nonInteractive: true }, runner);
    expect(result.kind).toBe("ran");
    if (result.kind !== "ran") return;
    expect(result.status).toBe(5);
    expect(result.stderr).toBe("boom");
  });
});

describe("uninstallFramework / restoreFramework — thin aliases", () => {
  it("uninstallFramework targets uninstall.py", () => {
    const calls: Call[] = [];
    const runner = makeRunner(calls, PYTHON3_OK);
    const result = uninstallFramework("/t", { nonInteractive: true }, runner);
    expect(result.kind).toBe("ran");
    if (result.kind !== "ran") return;
    expect(result.argv[1].endsWith(join("install", "uninstall.py"))).toBe(true);
  });

  it("restoreFramework targets restore.py", () => {
    const calls: Call[] = [];
    const runner = makeRunner(calls, PYTHON3_OK);
    const result = restoreFramework("/t", { nonInteractive: true }, runner);
    expect(result.kind).toBe("ran");
    if (result.kind !== "ran") return;
    expect(result.argv[1].endsWith(join("install", "restore.py"))).toBe(true);
  });
});

describe("CLI wiring", () => {
  const __dirname = dirname(fileURLToPath(import.meta.url));
  const src = readFileSync(resolve(__dirname, "..", "src", "index.ts"), "utf-8");

  it("registers the uninstall and restore commands", () => {
    expect(src).toContain('.command("uninstall")');
    expect(src).toContain('.command("restore")');
  });

  it("exposes --dry-run and --non-interactive on both teardown commands", () => {
    // Both flags appear (once per command); the actions forward them through.
    expect(src.match(/"--dry-run"/g)?.length).toBeGreaterThanOrEqual(2);
    expect(src.match(/"--non-interactive"/g)?.length).toBeGreaterThanOrEqual(2);
    expect(src).toContain("dryRun: opts.dryRun");
    expect(src).toContain("nonInteractive: opts.nonInteractive");
  });
});

describe("describeTeardownDegradation", () => {
  it("explains missing bundled assets per command", () => {
    const msg = describeTeardownDegradation("uninstall", { kind: "no-framework" });
    expect(msg).toContain("Cannot uninstall");
    expect(msg).toContain("bundled framework assets not found");
  });

  it("explains the no-python degradation with recovery paths", () => {
    const msg = describeTeardownDegradation("restore", { kind: "no-python" });
    expect(msg).toContain("Cannot restore");
    expect(msg).toContain("python3");
    expect(msg).toContain("pip install 2real-team-framework");
  });
});
