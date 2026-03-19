/**
 * Edge-case tests for YAML config file mode (issue #33).
 *
 * Covers edge cases identified during QA review of PR #23 that are not
 * covered by the existing integration tests in cli.test.ts.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import {
  existsSync,
  readFileSync,
  writeFileSync,
  mkdirSync,
  readdirSync,
} from "node:fs";
import { join } from "node:path";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";

import { loadYamlConfig, bootstrap, extractField } from "../src/bootstrap.js";

// ---------------------------------------------------------------------------
// loadYamlConfig — error paths
// ---------------------------------------------------------------------------

describe("loadYamlConfig error paths", () => {
  it("should throw for missing file", () => {
    expect(() => loadYamlConfig("/nonexistent/path.yaml")).toThrow(
      "Config file not found",
    );
  });

  it("should throw for invalid YAML syntax (malformed)", () => {
    const tmp = mkdtempSync(join(tmpdir(), "test-badyaml-"));
    const cfgPath = join(tmp, "bad.yaml");
    writeFileSync(cfgPath, "preset: [\n  invalid yaml here");
    expect(() => loadYamlConfig(cfgPath)).toThrow("Invalid YAML");
    rmSync(tmp, { recursive: true });
  });

  it("should throw for non-mapping YAML (array)", () => {
    const tmp = mkdtempSync(join(tmpdir(), "test-listyaml-"));
    const cfgPath = join(tmp, "list.yaml");
    writeFileSync(cfgPath, "- item1\n- item2\n");
    expect(() => loadYamlConfig(cfgPath)).toThrow("YAML mapping");
    rmSync(tmp, { recursive: true });
  });

  it("should throw for scalar YAML (string)", () => {
    const tmp = mkdtempSync(join(tmpdir(), "test-scalaryaml-"));
    const cfgPath = join(tmp, "scalar.yaml");
    writeFileSync(cfgPath, "just a string\n");
    expect(() => loadYamlConfig(cfgPath)).toThrow("YAML mapping");
    rmSync(tmp, { recursive: true });
  });

  it("should throw for null/empty YAML", () => {
    const tmp = mkdtempSync(join(tmpdir(), "test-nullyaml-"));
    const cfgPath = join(tmp, "null.yaml");
    writeFileSync(cfgPath, "");
    expect(() => loadYamlConfig(cfgPath)).toThrow("YAML mapping");
    rmSync(tmp, { recursive: true });
  });

  it("should throw for missing preset field", () => {
    const tmp = mkdtempSync(join(tmpdir(), "test-nopreset-yaml-"));
    const cfgPath = join(tmp, "nopreset.yaml");
    writeFileSync(cfgPath, "project_name: test\nteam_size: 3\n");
    expect(() => loadYamlConfig(cfgPath)).toThrow("preset");
    rmSync(tmp, { recursive: true });
  });

  it("should throw for empty string preset", () => {
    const tmp = mkdtempSync(join(tmpdir(), "test-emptypreset-"));
    const cfgPath = join(tmp, "empty.yaml");
    writeFileSync(cfgPath, 'preset: ""\n');
    expect(() => loadYamlConfig(cfgPath)).toThrow("preset");
    rmSync(tmp, { recursive: true });
  });

  it("should throw for whitespace-only preset", () => {
    const tmp = mkdtempSync(join(tmpdir(), "test-wspreset-"));
    const cfgPath = join(tmp, "ws.yaml");
    writeFileSync(cfgPath, 'preset: "   "\n');
    expect(() => loadYamlConfig(cfgPath)).toThrow("preset");
    rmSync(tmp, { recursive: true });
  });

  it("should throw for team_size as string", () => {
    const tmp = mkdtempSync(join(tmpdir(), "test-badsize-"));
    const cfgPath = join(tmp, "badsize.yaml");
    writeFileSync(cfgPath, "preset: library\nteam_size: not_a_number\n");
    expect(() => loadYamlConfig(cfgPath)).toThrow("valid integer");
    rmSync(tmp, { recursive: true });
  });
});

// ---------------------------------------------------------------------------
// loadYamlConfig — valid edge cases
// ---------------------------------------------------------------------------

describe("loadYamlConfig valid cases", () => {
  it("should load minimal config (preset only)", () => {
    const tmp = mkdtempSync(join(tmpdir(), "test-minyaml-"));
    const cfgPath = join(tmp, "minimal.yaml");
    writeFileSync(cfgPath, "preset: library\n");
    const cfg = loadYamlConfig(cfgPath);
    expect(cfg.preset).toBe("library");
    expect(cfg.project_name).toBeUndefined();
    expect(cfg.team_size).toBeUndefined();
    rmSync(tmp, { recursive: true });
  });

  it("should load full config with all fields", () => {
    const tmp = mkdtempSync(join(tmpdir(), "test-fullyaml-"));
    const cfgPath = join(tmp, "full.yaml");
    writeFileSync(
      cfgPath,
      [
        "preset: fullstack-monorepo",
        "project_name: my-project",
        "team_size: 5",
        "git_email_prefix: myorg",
        "target: /tmp/out",
        "skills:",
        "  - retro",
        "  - wave-start",
        "members:",
        "  - name: Alice Smith",
        "    role: Tech Lead",
        "    level: Staff",
        "  - name: Bob Jones",
        "",
      ].join("\n"),
    );
    const cfg = loadYamlConfig(cfgPath);
    expect(cfg.preset).toBe("fullstack-monorepo");
    expect(cfg.project_name).toBe("my-project");
    expect(cfg.team_size).toBe(5);
    expect(cfg.git_email_prefix).toBe("myorg");
    expect(cfg.skills).toEqual(["retro", "wave-start"]);
    expect(cfg.members).toHaveLength(2);
    expect(cfg.members![0].name).toBe("Alice Smith");
    expect(cfg.members![0].role).toBe("Tech Lead");
    expect(cfg.members![1].name).toBe("Bob Jones");
    rmSync(tmp, { recursive: true });
  });
});

// ---------------------------------------------------------------------------
// Behavioral edge cases — bootstrap with YAML config
// ---------------------------------------------------------------------------

describe("YAML config behavioral edge cases", () => {
  it("member overrides exceeding team_size should be silently ignored", async () => {
    const tmp = mkdtempSync(join(tmpdir(), "test-excess-"));
    const cfgPath = join(tmp, "config.yaml");
    writeFileSync(
      cfgPath,
      [
        "preset: library",
        "team_size: 2",
        "members:",
        "  - name: Alice Smith",
        "  - name: Bob Jones",
        "  - name: Charlie Brown",
        "  - name: Diana Prince",
        "",
      ].join("\n"),
    );
    const target = join(tmp, "output");
    mkdirSync(target);
    await bootstrap({
      config: cfgPath,
      target,
      interactive: false,
    });
    const rosterDir = join(target, ".claude", "team", "roster");
    const cards = readdirSync(rosterDir).filter((f) => f.endsWith(".md"));
    expect(cards.length).toBe(2);
    const allContent = cards
      .map((c) => readFileSync(join(rosterDir, c), "utf-8"))
      .join("\n");
    expect(allContent).toContain("Alice Smith");
    expect(allContent).toContain("Bob Jones");
    expect(allContent).not.toContain("Charlie Brown");
    expect(allContent).not.toContain("Diana Prince");
    rmSync(tmp, { recursive: true });
  });

  it("partial member overrides (only personality, no name/role) should work", async () => {
    const tmp = mkdtempSync(join(tmpdir(), "test-partial-"));
    const cfgPath = join(tmp, "config.yaml");
    writeFileSync(
      cfgPath,
      [
        "preset: library",
        "team_size: 3",
        "members:",
        "  - personality: Very analytical and detail-oriented.",
        "",
      ].join("\n"),
    );
    const target = join(tmp, "output");
    mkdirSync(target);
    await bootstrap({
      config: cfgPath,
      target,
      interactive: false,
    });
    const rosterDir = join(target, ".claude", "team", "roster");
    const cards = readdirSync(rosterDir).filter((f) => f.endsWith(".md"));
    expect(cards.length).toBe(3);
    rmSync(tmp, { recursive: true });
  });

  it("git_email_prefix should be applied to member emails", async () => {
    const tmp = mkdtempSync(join(tmpdir(), "test-emailprefix-"));
    const cfgPath = join(tmp, "config.yaml");
    writeFileSync(
      cfgPath,
      [
        "preset: library",
        "team_size: 2",
        "git_email_prefix: myorg",
        "members:",
        "  - name: Alice Smith",
        "",
      ].join("\n"),
    );
    const target = join(tmp, "output");
    mkdirSync(target);
    await bootstrap({
      config: cfgPath,
      target,
      interactive: false,
    });
    const rosterDir = join(target, ".claude", "team", "roster");
    const cards = readdirSync(rosterDir).filter((f) => f.endsWith(".md"));
    const aliceCard = cards.find((c) => c.includes("alice_smith"));
    expect(aliceCard).toBeDefined();
    const content = readFileSync(join(rosterDir, aliceCard!), "utf-8");
    expect(content).toContain("myorg+Alice.Smith@gmail.com");
    rmSync(tmp, { recursive: true });
  });
});
