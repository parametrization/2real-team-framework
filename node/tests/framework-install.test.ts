/**
 * Tests for the Node -> Python framework-install bridge: framework root
 * resolution, python detection, exact argv mapping, degradation results, the
 * unified-vs-legacy config detection, and version-from-package.json.
 */

import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { resolve, join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

import {
  resolveFrameworkRoot,
  findPython,
  buildBootstrapArgv,
  installFramework,
  describeInstallResult,
  type SpawnRunner,
  type SpawnResult,
} from "../src/framework-install.js";
import { isUnifiedConfig, parseUnifiedConfig } from "../src/bootstrap.js";
import { readPackageVersion } from "../src/version.js";

const __dirname = dirname(fileURLToPath(import.meta.url));
const REPO_FRAMEWORK = resolve(__dirname, "../../framework");
const PKG_ROOT = resolve(__dirname, "..");

interface Call {
  cmd: string;
  args: string[];
}

/** Runner that answers python probes and the bootstrap call with `status`. */
function makeRunner(
  calls: Call[],
  pythonResults: Record<string, SpawnResult>,
  bootstrapResult: SpawnResult = { status: 0, stdout: "", stderr: "" },
): SpawnRunner {
  return (cmd, args) => {
    calls.push({ cmd, args });
    if (args.length === 1 && args[0] === "--version") {
      return pythonResults[cmd] ?? { status: null, error: new Error(`ENOENT: ${cmd}`) };
    }
    return bootstrapResult;
  };
}

const PYTHON3_OK: Record<string, SpawnResult> = { python3: { status: 0 } };

describe("resolveFrameworkRoot", () => {
  it("resolves the repo-root framework/ in a dev checkout", () => {
    const root = resolveFrameworkRoot();
    expect(root).not.toBeNull();
    // Either the package-local bundle (post-prepack) or the repo checkout.
    expect([resolve(PKG_ROOT, "framework"), REPO_FRAMEWORK]).toContain(root);
  });
});

describe("findPython", () => {
  it("prefers python3", () => {
    const calls: Call[] = [];
    const runner = makeRunner(calls, { python3: { status: 0 }, python: { status: 0 } });
    expect(findPython(runner)).toBe("python3");
    expect(calls).toHaveLength(1);
  });

  it("falls back to python when python3 is missing", () => {
    const calls: Call[] = [];
    const runner = makeRunner(calls, {
      python3: { status: null, error: new Error("ENOENT") },
      python: { status: 0 },
    });
    expect(findPython(runner)).toBe("python");
    expect(calls.map((c) => c.cmd)).toEqual(["python3", "python"]);
  });

  it("returns null when neither interpreter runs", () => {
    const calls: Call[] = [];
    const runner = makeRunner(calls, {});
    expect(findPython(runner)).toBeNull();
    expect(calls.map((c) => c.cmd)).toEqual(["python3", "python"]);
  });

  it("treats a nonzero exit as missing", () => {
    const runner = makeRunner([], { python3: { status: 1 }, python: { status: 0 } });
    expect(findPython(runner)).toBe("python");
  });
});

describe("buildBootstrapArgv — exact flag mapping", () => {
  const bootstrapPath = join("/fw", "install", "bootstrap.py");

  it("maps the full flag set exactly", () => {
    const argv = buildBootstrapArgv("python3", "/fw", "/target", {
      installConfig: "/cfg/install.yaml",
      owner: "acme",
      mergeModel: "wave-branch",
      withOntology: true,
    });
    expect(argv).toEqual([
      "python3",
      bootstrapPath,
      "/target",
      "--no-team",
      "--non-interactive",
      "--shell",
      "bash",
      "--install-config",
      "/cfg/install.yaml",
      "--owner",
      "acme",
      "--merge-model",
      "wave-branch",
      "--with-ontology",
    ]);
  });

  it("always passes --no-team and --non-interactive with minimal options", () => {
    const argv = buildBootstrapArgv("python3", "/fw", "/target");
    expect(argv).toEqual([
      "python3",
      bootstrapPath,
      "/target",
      "--no-team",
      "--non-interactive",
      "--shell",
      "bash",
    ]);
  });

  it("tri-state ontology: false maps to --no-ontology", () => {
    const argv = buildBootstrapArgv("python3", "/fw", "/t", { withOntology: false });
    expect(argv).toContain("--no-ontology");
    expect(argv).not.toContain("--with-ontology");
  });

  it("tri-state ontology: unset forwards neither flag", () => {
    const argv = buildBootstrapArgv("python3", "/fw", "/t", {});
    expect(argv).not.toContain("--with-ontology");
    expect(argv).not.toContain("--no-ontology");
  });

  it("maps --dry-run", () => {
    expect(buildBootstrapArgv("python3", "/fw", "/t", { dryRun: true })).toContain("--dry-run");
  });
});

describe("installFramework", () => {
  it("subprocesses the bundled bootstrap with the mapped argv", () => {
    const calls: Call[] = [];
    const runner = makeRunner(calls, PYTHON3_OK, { status: 0, stdout: "ok", stderr: "" });
    const result = installFramework(
      "/target",
      { owner: "acme", mergeModel: "direct-to-main", withOntology: false },
      runner,
    );
    expect(result.kind).toBe("ran");
    if (result.kind !== "ran") return;
    expect(result.status).toBe(0);
    const root = resolveFrameworkRoot()!;
    expect(result.argv).toEqual([
      "python3",
      join(root, "install", "bootstrap.py"),
      "/target",
      "--no-team",
      "--non-interactive",
      "--shell",
      "bash",
      "--owner",
      "acme",
      "--merge-model",
      "direct-to-main",
      "--no-ontology",
    ]);
    // Last spawn is the bootstrap subprocess itself, with the same argv.
    const last = calls[calls.length - 1];
    expect([last.cmd, ...last.args]).toEqual(result.argv);
  });

  it("degrades to no-python without invoking the bootstrapper", () => {
    const calls: Call[] = [];
    const runner = makeRunner(calls, {});
    const result = installFramework("/target", {}, runner);
    expect(result).toEqual({ kind: "no-python" });
    // Only the two interpreter probes — never the bootstrap subprocess.
    expect(calls.map((c) => c.cmd)).toEqual(["python3", "python"]);
  });

  it("surfaces a nonzero bootstrap exit", () => {
    const runner = makeRunner([], PYTHON3_OK, { status: 3, stdout: "", stderr: "boom" });
    const result = installFramework("/target", {}, runner);
    expect(result.kind).toBe("ran");
    if (result.kind !== "ran") return;
    expect(result.status).toBe(3);
    expect(result.stderr).toBe("boom");
  });
});

describe("describeInstallResult", () => {
  it("explains the no-python degradation with recovery paths", () => {
    const msg = describeInstallResult({ kind: "no-python" });
    expect(msg).toContain("python3");
    expect(msg).toContain("pip install 2real-team-framework");
    expect(msg).toContain("team scaffolding");
  });

  it("explains missing bundled assets", () => {
    const msg = describeInstallResult({ kind: "no-framework" });
    expect(msg).toContain("bundled assets not found");
  });

  it("reports a nonzero exit with detail", () => {
    const msg = describeInstallResult({
      kind: "ran",
      status: 2,
      stdout: "",
      stderr: "traceback",
      argv: [],
    });
    expect(msg).toContain("exit 2");
    expect(msg).toContain("traceback");
  });

  it("reports success", () => {
    const msg = describeInstallResult({ kind: "ran", status: 0, stdout: "", stderr: "", argv: [] });
    expect(msg).toContain("Installed the framework runtime");
  });
});

describe("unified vs legacy config detection", () => {
  it("detects marker keys as unified", () => {
    for (const raw of [
      { version: 1 },
      { repo: { expect: "fresh" } },
      { scm: { owner: "acme" } },
      { ontology: { enabled: false } },
      { children: [] },
      { pre_push: { mode: "noop" } },
    ]) {
      expect(isUnifiedConfig(raw as Record<string, unknown>)).toBe(true);
    }
  });

  it("detects team/project mappings as unified", () => {
    expect(isUnifiedConfig({ team: { preset: "library" } })).toBe(true);
    expect(isUnifiedConfig({ project: { name: "x" } })).toBe(true);
  });

  it("treats the legacy flat team schema as legacy", () => {
    expect(isUnifiedConfig({ preset: "library", team_size: 5 })).toBe(false);
    expect(isUnifiedConfig({ preset: "library", members: [{ name: "A B" }] })).toBe(false);
  });

  it("does not treat a non-mapping team key as unified", () => {
    expect(isUnifiedConfig({ team: ["a"] })).toBe(false);
  });

  it("parseUnifiedConfig extracts the team-relevant subset", () => {
    const cfg = parseUnifiedConfig({
      version: 1,
      project: { name: "acme-app" },
      scm: { owner: "acme" },
      team: { enabled: true, preset: "library", size: 4 },
    });
    expect(cfg).toEqual({
      teamEnabled: true,
      preset: "library",
      teamSize: 4,
      projectName: "acme-app",
      owner: "acme",
    });
  });

  it("parseUnifiedConfig defaults team.enabled to true and honors false", () => {
    expect(parseUnifiedConfig({ version: 1 }).teamEnabled).toBe(true);
    expect(parseUnifiedConfig({ team: { enabled: false } }).teamEnabled).toBe(false);
  });
});

describe("CLI version", () => {
  it("reads the version from package.json (no hardcoded string)", () => {
    const pkg = JSON.parse(readFileSync(join(PKG_ROOT, "package.json"), "utf-8"));
    expect(readPackageVersion()).toBe(pkg.version);
    expect(readPackageVersion()).toMatch(/^\d+\.\d+\.\d+/);
  });

  it("index.ts wires program.version() to readPackageVersion", () => {
    const src = readFileSync(join(PKG_ROOT, "src", "index.ts"), "utf-8");
    expect(src).toContain(".version(readPackageVersion())");
    expect(src).not.toMatch(/\.version\("\d/);
  });
});
