/**
 * Integration tests for `init` + the framework bridge: hook invocation with
 * mapped options, unified-config forwarding (--install-config), team.enabled
 * false runtime-only path, --no-hooks, and the python3-missing degradation
 * path (team scaffolding must still land).
 *
 * `installFramework` is mocked (spawn never runs); everything else is real.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { existsSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { tmpdir } from "node:os";

vi.mock("../src/framework-install.js", async (importOriginal) => {
  const mod = await importOriginal<typeof import("../src/framework-install.js")>();
  return {
    ...mod,
    installFramework: vi.fn(() => ({
      kind: "ran",
      status: 0,
      stdout: "",
      stderr: "",
      argv: [],
    })),
  };
});

import { bootstrap } from "../src/bootstrap.js";
import { installFramework } from "../src/framework-install.js";

const installFrameworkMock = vi.mocked(installFramework);

let target: string;
let logSpy: ReturnType<typeof vi.spyOn>;
let warnSpy: ReturnType<typeof vi.spyOn>;

beforeEach(() => {
  target = mkdtempSync(join(tmpdir(), "2real-bridge-"));
  installFrameworkMock.mockClear();
  installFrameworkMock.mockReturnValue({
    kind: "ran",
    status: 0,
    stdout: "",
    stderr: "",
    argv: [],
  });
  logSpy = vi.spyOn(console, "log").mockImplementation(() => {});
  warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});
});

afterEach(() => {
  logSpy.mockRestore();
  warnSpy.mockRestore();
  rmSync(target, { recursive: true, force: true });
});

function output(spy: ReturnType<typeof vi.spyOn>): string {
  return spy.mock.calls.map((c) => c.join(" ")).join("\n");
}

describe("init --with-hooks bridge", () => {
  it("invokes the bridge by default with mapped options", async () => {
    await bootstrap({
      preset: "library",
      target,
      interactive: false,
      owner: "acme",
      mergeModel: "wave-branch",
      withOntology: true,
    });
    expect(installFrameworkMock).toHaveBeenCalledTimes(1);
    expect(installFrameworkMock).toHaveBeenCalledWith(resolve(target), {
      owner: "acme",
      mergeModel: "wave-branch",
      installConfig: undefined,
      withOntology: true,
    });
    expect(existsSync(join(target, ".claude", "team", "charter.md"))).toBe(true);
  });

  it("skips the bridge with --no-hooks", async () => {
    await bootstrap({ preset: "library", target, interactive: false, withHooks: false });
    expect(installFrameworkMock).not.toHaveBeenCalled();
    expect(existsSync(join(target, ".claude", "team", "charter.md"))).toBe(true);
  });

  it("forwards a unified config as --install-config and takes team/scm fields from it", async () => {
    const cfgPath = join(target, "install.yaml");
    writeFileSync(
      cfgPath,
      [
        "version: 1",
        "project:",
        "  name: acme-app",
        "scm:",
        "  owner: acme",
        "team:",
        "  preset: library",
        "  size: 4",
      ].join("\n") + "\n",
    );
    await bootstrap({ config: cfgPath, target, interactive: true });
    expect(installFrameworkMock).toHaveBeenCalledWith(resolve(target), {
      owner: "acme",
      mergeModel: undefined,
      installConfig: resolve(cfgPath),
      withOntology: undefined,
    });
    expect(existsSync(join(target, ".claude", "team", "charter.md"))).toBe(true);
    expect(output(logSpy)).toContain("acme-app");
  });

  it("CLI flags win over the unified YAML", async () => {
    const cfgPath = join(target, "install.yaml");
    writeFileSync(cfgPath, "version: 1\nscm:\n  owner: yaml-owner\nteam:\n  preset: library\n");
    await bootstrap({ config: cfgPath, target, interactive: false, owner: "flag-owner" });
    expect(installFrameworkMock.mock.calls[0][1]).toMatchObject({ owner: "flag-owner" });
  });

  it("does not forward a legacy config as --install-config", async () => {
    const cfgPath = join(target, "team.yaml");
    writeFileSync(cfgPath, "preset: library\nteam_size: 3\n");
    await bootstrap({ config: cfgPath, target, interactive: false });
    expect(installFrameworkMock.mock.calls[0][1]).toMatchObject({ installConfig: undefined });
  });

  it("team.enabled false installs the runtime only (no team scaffolding)", async () => {
    const cfgPath = join(target, "install.yaml");
    writeFileSync(cfgPath, "version: 1\nteam:\n  enabled: false\n");
    await bootstrap({ config: cfgPath, target, interactive: false });
    expect(installFrameworkMock).toHaveBeenCalledWith(resolve(target), {
      owner: undefined,
      mergeModel: undefined,
      installConfig: resolve(cfgPath),
      withOntology: undefined,
    });
    expect(existsSync(join(target, ".claude", "team"))).toBe(false);
    expect(output(logSpy)).toContain("skipping team scaffolding");
  });
});

describe("python3-missing degradation", () => {
  it("still installs the team scaffolding and explains what was skipped", async () => {
    installFrameworkMock.mockReturnValue({ kind: "no-python" });
    await bootstrap({ preset: "library", target, interactive: false });

    // Team layer landed despite the missing runtime.
    expect(existsSync(join(target, ".claude", "team", "charter.md"))).toBe(true);
    expect(existsSync(join(target, "CLAUDE.md"))).toBe(true);
    expect(output(logSpy)).toContain("Team framework bootstrapped");

    // Clear degradation message: what was skipped and how to get the runtime.
    const warned = output(warnSpy);
    expect(warned).toContain("no Python 3 interpreter found");
    expect(warned).toContain("python3");
    expect(warned).toContain("pip install 2real-team-framework");
  });

  it("reports a failed bootstrap subprocess without aborting", async () => {
    installFrameworkMock.mockReturnValue({
      kind: "ran",
      status: 2,
      stdout: "",
      stderr: "explosion",
      argv: [],
    });
    await bootstrap({ preset: "library", target, interactive: false });
    expect(existsSync(join(target, ".claude", "team", "charter.md"))).toBe(true);
    const warned = output(warnSpy);
    expect(warned).toContain("exit 2");
    expect(warned).toContain("explosion");
  });
});
