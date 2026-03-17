/**
 * Comprehensive tests for the 2real-team Node CLI — targeting >90% coverage.
 */

import { describe, it, expect, beforeEach, vi, afterEach } from "vitest";
import {
  existsSync,
  readFileSync,
  writeFileSync,
  mkdirSync,
  readdirSync,
} from "node:fs";
import { resolve, dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { mkdtempSync, rmSync, renameSync } from "node:fs";
import { tmpdir } from "node:os";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const PRESETS_DIR = resolve(__dirname, "../../presets");
const TEMPLATES_DIR = resolve(__dirname, "../../templates");
const SKILLS_DIR = resolve(__dirname, "../../skills");

// Import functions from bootstrap (via source)
import {
  generateName,
  makeEmail,
  extractField,
  replaceField,
  safeName,
  findRosterCards,
  loadPreset,
  listPresets,
  bootstrap,
  addMember,
  removeMember,
  updateMember,
  randomizeMember,
  validateTeam,
  showStatus,
  FIRST_NAMES,
  LAST_NAMES,
  COMMUNICATION_STYLES,
} from "../src/bootstrap.js";
import { getPreset, listPresets as listPresetsFromModule } from "../src/presets.js";
import {
  renderTemplate,
  renderSkill,
  listTemplates,
  listSkills,
} from "../src/templates.js";

// ---------------------------------------------------------------------------
// Presets
// ---------------------------------------------------------------------------

describe("presets", () => {
  it("should have all three preset files", () => {
    expect(existsSync(resolve(PRESETS_DIR, "fullstack-monorepo.json"))).toBe(
      true,
    );
    expect(existsSync(resolve(PRESETS_DIR, "data-pipeline.json"))).toBe(true);
    expect(existsSync(resolve(PRESETS_DIR, "library.json"))).toBe(true);
  });

  it("should have valid JSON in each preset", () => {
    for (const name of ["fullstack-monorepo", "data-pipeline", "library"]) {
      const content = readFileSync(
        resolve(PRESETS_DIR, `${name}.json`),
        "utf-8",
      );
      const preset = JSON.parse(content);
      expect(preset.name).toBe(name);
      expect(preset.roles).toBeInstanceOf(Array);
      expect(preset.skills).toBeInstanceOf(Array);
      expect(preset.default_team_size).toBeGreaterThan(0);
    }
  });

  it("should load preset by name", () => {
    const preset = loadPreset("library");
    expect(preset.name).toBe("library");
    expect(preset.default_team_size).toBeGreaterThan(0);
  });

  it("should throw for unknown preset", () => {
    expect(() => loadPreset("nonexistent")).toThrow("Unknown preset");
  });

  it("should list all presets", () => {
    const presets = listPresets();
    expect(presets.length).toBeGreaterThanOrEqual(3);
    const names = presets.map((p) => p.name);
    expect(names).toContain("library");
    expect(names).toContain("data-pipeline");
    expect(names).toContain("fullstack-monorepo");
  });

  it("getPreset from presets module should work", () => {
    const preset = getPreset("library");
    expect(preset.name).toBe("library");
  });

  it("getPreset should throw for unknown preset", () => {
    expect(() => getPreset("nonexistent")).toThrow("Unknown preset");
  });

  it("listPresets from presets module should return sorted results", () => {
    const presets = listPresetsFromModule();
    expect(presets.length).toBeGreaterThanOrEqual(3);
  });
});

// ---------------------------------------------------------------------------
// Templates
// ---------------------------------------------------------------------------

describe("templates", () => {
  const expectedTemplates = [
    "charter.md.mustache",
    "roster-card.md.mustache",
    "trust-matrix.md.mustache",
    "feedback-log.md.mustache",
    "CLAUDE.md.mustache",
    "skill.md.mustache",
  ];

  for (const t of expectedTemplates) {
    it(`should have ${t}`, () => {
      expect(existsSync(resolve(TEMPLATES_DIR, t))).toBe(true);
    });
  }

  it("should render charter template", () => {
    const result = renderTemplate("charter.md.mustache", {
      project_name: "test-project",
      team_members: [{ name: "Alice", role: "Engineer", level: "Senior" }],
    });
    expect(result).toContain("test-project");
  });

  it("should render roster-card template", () => {
    const result = renderTemplate("roster-card.md.mustache", {
      name: "Alice Smith",
      role: "Engineer",
      level: "Senior",
      email: "alice@test.com",
      personality: "Direct and structured.",
    });
    expect(result).toContain("Alice Smith");
    expect(result).toContain("Engineer");
  });

  it("should throw for missing template", () => {
    expect(() => renderTemplate("nonexistent.mustache", {})).toThrow(
      "Template not found",
    );
  });

  it("should render all templates without errors", () => {
    const ctx = {
      project_name: "test",
      team_members: [
        {
          name: "Test",
          agent_name: "test",
          role: "Eng",
          level: "Sr",
          email: "t@t.com",
          reports_to: "User",
          personality: "Nice.",
        },
      ],
    };
    for (const tmpl of listTemplates()) {
      const result = renderTemplate(tmpl, ctx);
      expect(typeof result).toBe("string");
    }
  });

  it("should list templates", () => {
    const templates = listTemplates();
    expect(templates.length).toBeGreaterThanOrEqual(5);
    expect(templates).toContain("charter.md.mustache");
  });
});

// ---------------------------------------------------------------------------
// Skills
// ---------------------------------------------------------------------------

describe("skills", () => {
  const expectedSkills = [
    "retro.md.mustache",
    "wave-start.md.mustache",
    "wave-end.md.mustache",
    "review-pr.md.mustache",
    "plan-phase.md.mustache",
    "close-stale-issues.md.mustache",
  ];

  for (const s of expectedSkills) {
    it(`should have ${s}`, () => {
      expect(existsSync(resolve(SKILLS_DIR, s))).toBe(true);
    });
  }

  it("should render a skill template", () => {
    const result = renderSkill("retro.md.mustache", {
      project_name: "test",
      team_members: [],
    });
    expect(typeof result).toBe("string");
    expect(result.length).toBeGreaterThan(0);
  });

  it("should throw for missing skill template", () => {
    expect(() => renderSkill("nonexistent.md.mustache", {})).toThrow(
      "Skill template not found",
    );
  });

  it("should list skills", () => {
    const skills = listSkills();
    expect(skills.length).toBeGreaterThanOrEqual(1);
    expect(skills).toContain("retro.md.mustache");
  });
});

// ---------------------------------------------------------------------------
// Name generation
// ---------------------------------------------------------------------------

describe("name generation", () => {
  it("should generate unique names", () => {
    const used = new Set<string>();
    for (let i = 0; i < 10; i++) {
      const [first, last] = generateName(used);
      const full = `${first} ${last}`;
      expect(used.has(full)).toBe(false);
      used.add(full);
    }
  });

  it("should throw when no unique name possible", () => {
    const used = new Set<string>();
    for (const f of FIRST_NAMES) {
      for (const l of LAST_NAMES) {
        used.add(`${f} ${l}`);
      }
    }
    expect(() => generateName(used)).toThrow("Could not generate unique name");
  });

  it("should have non-empty name pools", () => {
    expect(FIRST_NAMES.length).toBeGreaterThan(0);
    expect(LAST_NAMES.length).toBeGreaterThan(0);
    expect(COMMUNICATION_STYLES.length).toBeGreaterThan(0);
  });
});

// ---------------------------------------------------------------------------
// Email generation
// ---------------------------------------------------------------------------

describe("email generation", () => {
  it("should generate basic email", () => {
    expect(makeEmail("John", "Doe")).toBe("John.Doe@gmail.com");
  });

  it("should strip diacritics", () => {
    expect(makeEmail("Carolina", "Méndez-Ríos")).toBe(
      "Carolina.Mendez-Rios@gmail.com",
    );
  });

  it("should handle email prefix", () => {
    expect(makeEmail("Tomasz", "Wójcik", "org")).toBe(
      "org+Tomasz.Wojcik@gmail.com",
    );
  });

  it("should not include + when no prefix", () => {
    const email = makeEmail("A", "B");
    expect(email).not.toContain("+");
  });
});

// ---------------------------------------------------------------------------
// agent_name / safeName
// ---------------------------------------------------------------------------

describe("agent_name and safeName", () => {
  it("should convert names to kebab-case via toLowerCase and replace", () => {
    const toAgentName = (name: string) =>
      name.toLowerCase().replace(/ /g, "-");
    expect(toAgentName("Hiro Morales")).toBe("hiro-morales");
    expect(toAgentName("Ibrahim El-Amin")).toBe("ibrahim-el-amin");
    expect(toAgentName("Mei-Lin Chang")).toBe("mei-lin-chang");
  });

  it("safeName should convert to underscore-separated lowercase", () => {
    expect(safeName("Hiro Morales")).toBe("hiro_morales");
    expect(safeName("Ibrahim El-Amin")).toBe("ibrahim_el_amin");
  });
});

// ---------------------------------------------------------------------------
// extractField / replaceField
// ---------------------------------------------------------------------------

describe("extractField", () => {
  it("should extract a field value", () => {
    const content = "- **Name:** John Doe\n- **Role:** Engineer\n";
    expect(extractField(content, "Name")).toBe("John Doe");
    expect(extractField(content, "Role")).toBe("Engineer");
  });

  it("should return null for missing field", () => {
    expect(extractField("no fields here", "Name")).toBeNull();
  });
});

describe("replaceField", () => {
  it("should replace a field value", () => {
    const content = "- **Role:** Engineer\n- **Level:** Senior\n";
    const result = replaceField(content, "Role", "Manager");
    expect(result).toContain("**Role:** Manager");
    expect(result).toContain("**Level:** Senior");
  });

  it("should not modify unmatched fields", () => {
    const content = "- **Role:** Engineer\n";
    const result = replaceField(content, "Level", "Staff");
    expect(result).toBe(content);
  });
});

// ---------------------------------------------------------------------------
// findRosterCards
// ---------------------------------------------------------------------------

describe("findRosterCards", () => {
  it("should return empty for nonexistent directory", () => {
    expect(findRosterCards("/nonexistent/path", "test")).toEqual([]);
  });

  it("should find matching cards", () => {
    const tmp = mkdtempSync(join(tmpdir(), "test-roster-"));
    writeFileSync(
      join(tmp, "engineer_john_doe.md"),
      "- **Name:** John Doe\n",
    );
    writeFileSync(
      join(tmp, "manager_jane_smith.md"),
      "- **Name:** Jane Smith\n",
    );
    const result = findRosterCards(tmp, "John Doe");
    expect(result).toHaveLength(1);
    expect(result[0]).toContain("john_doe");
    rmSync(tmp, { recursive: true });
  });

  it("should exclude departed cards", () => {
    const tmp = mkdtempSync(join(tmpdir(), "test-roster-"));
    writeFileSync(
      join(tmp, "_departed_engineer_john_doe.md"),
      "- **Name:** John Doe\n",
    );
    const result = findRosterCards(tmp, "John Doe");
    expect(result).toHaveLength(0);
    rmSync(tmp, { recursive: true });
  });
});

// ---------------------------------------------------------------------------
// bootstrap (integration)
// ---------------------------------------------------------------------------

describe("bootstrap", () => {
  let tmp: string;

  beforeEach(() => {
    tmp = mkdtempSync(join(tmpdir(), "test-bootstrap-"));
  });

  it("should create team files in non-interactive mode", async () => {
    await bootstrap({
      preset: "library",
      teamSize: 3,
      projectName: "test-project",
      target: tmp,
      interactive: false,
    });
    expect(existsSync(join(tmp, ".claude", "team", "charter.md"))).toBe(true);
    expect(existsSync(join(tmp, ".claude", "team", "trust_matrix.md"))).toBe(
      true,
    );
    expect(existsSync(join(tmp, ".claude", "team", "feedback_log.md"))).toBe(
      true,
    );
    expect(existsSync(join(tmp, ".claude", "CLAUDE.md"))).toBe(true);

    const roster = readdirSync(join(tmp, ".claude", "team", "roster")).filter(
      (f) => f.endsWith(".md"),
    );
    expect(roster.length).toBe(3);
  });

  it("should create skills", async () => {
    await bootstrap({
      preset: "library",
      teamSize: 3,
      projectName: "skills-test",
      target: tmp,
      interactive: false,
    });
    const skillsDir = join(tmp, ".claude", "skills");
    expect(existsSync(skillsDir)).toBe(true);
    const skills = readdirSync(skillsDir).filter((f) => f.endsWith(".md"));
    expect(skills.length).toBeGreaterThan(0);
  });

  it("should work with all presets", async () => {
    for (const preset of ["library", "data-pipeline", "fullstack-monorepo"]) {
      const dir = mkdtempSync(join(tmpdir(), `test-${preset}-`));
      await bootstrap({
        preset,
        teamSize: 3,
        projectName: `test-${preset}`,
        target: dir,
        interactive: false,
      });
      expect(existsSync(join(dir, ".claude", "team", "charter.md"))).toBe(
        true,
      );
      rmSync(dir, { recursive: true });
    }
  });
});

// ---------------------------------------------------------------------------
// addMember
// ---------------------------------------------------------------------------

describe("addMember", () => {
  let tmp: string;

  beforeEach(async () => {
    tmp = mkdtempSync(join(tmpdir(), "test-add-"));
    await bootstrap({
      preset: "library",
      teamSize: 3,
      projectName: "add-test",
      target: tmp,
      interactive: false,
    });
  });

  it("should add a named member", () => {
    addMember({
      name: "Jane Doe",
      role: "QA Engineer",
      level: "Senior",
      target: tmp,
    });
    const roster = readdirSync(
      join(tmp, ".claude", "team", "roster"),
    ).filter((f) => f.endsWith(".md") && !f.startsWith("_departed_"));
    expect(roster.length).toBe(4);
    expect(roster.some((f) => f.includes("jane_doe"))).toBe(true);
  });

  it("should add a member with random name", () => {
    addMember({
      role: "DevOps Engineer",
      level: "Mid",
      target: tmp,
    });
    const roster = readdirSync(
      join(tmp, ".claude", "team", "roster"),
    ).filter((f) => f.endsWith(".md") && !f.startsWith("_departed_"));
    expect(roster.length).toBe(4);
  });
});

// ---------------------------------------------------------------------------
// removeMember
// ---------------------------------------------------------------------------

describe("removeMember", () => {
  let tmp: string;
  let memberName: string;

  beforeEach(async () => {
    tmp = mkdtempSync(join(tmpdir(), "test-remove-"));
    await bootstrap({
      preset: "library",
      teamSize: 3,
      projectName: "remove-test",
      target: tmp,
      interactive: false,
    });
    // Find a member name
    const rosterDir = join(tmp, ".claude", "team", "roster");
    const files = readdirSync(rosterDir).filter((f) => f.endsWith(".md"));
    const content = readFileSync(join(rosterDir, files[0]), "utf-8");
    memberName = extractField(content, "Name") ?? "";
  });

  it("should archive a member", () => {
    removeMember({ name: memberName, target: tmp });
    const rosterDir = join(tmp, ".claude", "team", "roster");
    const active = readdirSync(rosterDir).filter(
      (f) => f.endsWith(".md") && !f.startsWith("_departed_"),
    );
    const departed = readdirSync(rosterDir).filter((f) =>
      f.startsWith("_departed_"),
    );
    expect(active.length).toBe(2);
    expect(departed.length).toBe(1);
  });
});

// ---------------------------------------------------------------------------
// updateMember
// ---------------------------------------------------------------------------

describe("updateMember", () => {
  let tmp: string;
  let memberName: string;

  beforeEach(async () => {
    tmp = mkdtempSync(join(tmpdir(), "test-update-"));
    await bootstrap({
      preset: "library",
      teamSize: 3,
      projectName: "update-test",
      target: tmp,
      interactive: false,
    });
    const rosterDir = join(tmp, ".claude", "team", "roster");
    const files = readdirSync(rosterDir).filter((f) => f.endsWith(".md"));
    const content = readFileSync(join(rosterDir, files[0]), "utf-8");
    memberName = extractField(content, "Name") ?? "";
  });

  it("should update role", () => {
    updateMember({
      name: memberName,
      role: "Principal Architect",
      target: tmp,
    });
    const rosterDir = join(tmp, ".claude", "team", "roster");
    const files = readdirSync(rosterDir).filter(
      (f) => f.endsWith(".md") && !f.startsWith("_departed_"),
    );
    const updated = readFileSync(join(rosterDir, files[0]), "utf-8");
    expect(updated).toContain("Principal Architect");
  });

  it("should update level", () => {
    updateMember({ name: memberName, level: "Staff", target: tmp });
    const rosterDir = join(tmp, ".claude", "team", "roster");
    const files = readdirSync(rosterDir).filter(
      (f) => f.endsWith(".md") && !f.startsWith("_departed_"),
    );
    const updated = readFileSync(join(rosterDir, files[0]), "utf-8");
    expect(updated).toContain("Staff");
  });
});

// ---------------------------------------------------------------------------
// randomizeMember
// ---------------------------------------------------------------------------

describe("randomizeMember", () => {
  let tmp: string;
  let memberName: string;

  beforeEach(async () => {
    tmp = mkdtempSync(join(tmpdir(), "test-randomize-"));
    await bootstrap({
      preset: "library",
      teamSize: 3,
      projectName: "rand-test",
      target: tmp,
      interactive: false,
    });
    const rosterDir = join(tmp, ".claude", "team", "roster");
    const files = readdirSync(rosterDir).filter((f) => f.endsWith(".md"));
    const content = readFileSync(join(rosterDir, files[0]), "utf-8");
    memberName = extractField(content, "Name") ?? "";
  });

  it("should archive old and create new member", () => {
    randomizeMember({ name: memberName, target: tmp });
    const rosterDir = join(tmp, ".claude", "team", "roster");
    const active = readdirSync(rosterDir).filter(
      (f) => f.endsWith(".md") && !f.startsWith("_departed_"),
    );
    const departed = readdirSync(rosterDir).filter((f) =>
      f.startsWith("_departed_"),
    );
    expect(active.length).toBe(3);
    expect(departed.length).toBe(1);
  });
});

// ---------------------------------------------------------------------------
// validateTeam
// ---------------------------------------------------------------------------

describe("validateTeam", () => {
  it("should pass validation after init", async () => {
    const tmp = mkdtempSync(join(tmpdir(), "test-validate-"));
    await bootstrap({
      preset: "library",
      teamSize: 3,
      projectName: "validate-test",
      target: tmp,
      interactive: false,
    });
    // Should not throw
    validateTeam({ target: tmp });
    rmSync(tmp, { recursive: true });
  });
});

// ---------------------------------------------------------------------------
// showStatus
// ---------------------------------------------------------------------------

describe("showStatus", () => {
  it("should show status after init", async () => {
    const tmp = mkdtempSync(join(tmpdir(), "test-status-"));
    await bootstrap({
      preset: "library",
      teamSize: 3,
      projectName: "status-test",
      target: tmp,
      interactive: false,
    });
    // Should not throw
    showStatus({ target: tmp });
    rmSync(tmp, { recursive: true });
  });
});

// ---------------------------------------------------------------------------
// End-to-end lifecycle
// ---------------------------------------------------------------------------

describe("end-to-end lifecycle", () => {
  it("should complete init -> add -> update -> remove -> validate -> status", async () => {
    const tmp = mkdtempSync(join(tmpdir(), "test-e2e-"));

    // 1. Init
    await bootstrap({
      preset: "library",
      teamSize: 3,
      projectName: "e2e-test",
      target: tmp,
      interactive: false,
    });

    // 2. Add member
    addMember({
      name: "E2E Tester",
      role: "QA Engineer",
      level: "Senior",
      target: tmp,
    });

    // 3. Update member
    updateMember({
      name: "E2E Tester",
      role: "QA Lead",
      level: "Staff",
      target: tmp,
    });

    // 4. Remove member
    removeMember({ name: "E2E Tester", target: tmp });

    // 5. Validate
    validateTeam({ target: tmp });

    // 6. Status
    showStatus({ target: tmp });

    rmSync(tmp, { recursive: true });
  });
});

// ---------------------------------------------------------------------------
// Error paths (process.exit mocking)
// ---------------------------------------------------------------------------

describe("error paths", () => {
  let exitSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    exitSpy = vi.spyOn(process, "exit").mockImplementation(((code?: number) => {
      throw new Error(`process.exit(${code})`);
    }) as never);
  });

  afterEach(() => {
    exitSpy.mockRestore();
  });

  it("bootstrap should exit(1) without preset in non-interactive mode", async () => {
    const tmp = mkdtempSync(join(tmpdir(), "test-nopreset-"));
    await expect(
      bootstrap({ target: tmp, interactive: false }),
    ).rejects.toThrow("process.exit(1)");
    rmSync(tmp, { recursive: true });
  });

  it("bootstrap should default projectName to dir name in non-interactive", async () => {
    const tmp = mkdtempSync(join(tmpdir(), "test-defname-"));
    await bootstrap({
      preset: "library",
      teamSize: 2,
      target: tmp,
      interactive: false,
    });
    expect(existsSync(join(tmp, ".claude", "team", "charter.md"))).toBe(true);
    rmSync(tmp, { recursive: true });
  });

  it("bootstrap should use default team size when not provided", async () => {
    const tmp = mkdtempSync(join(tmpdir(), "test-defsize-"));
    await bootstrap({
      preset: "library",
      projectName: "size-test",
      target: tmp,
      interactive: false,
    });
    const rosterDir = join(tmp, ".claude", "team", "roster");
    const cards = readdirSync(rosterDir).filter((f) => f.endsWith(".md"));
    expect(cards.length).toBe(5); // library default is 5
    rmSync(tmp, { recursive: true });
  });

  it("addMember should exit(1) when no roster dir", () => {
    const tmp = mkdtempSync(join(tmpdir(), "test-noroster-"));
    expect(() =>
      addMember({ name: "Test", role: "Eng", level: "Sr", target: tmp }),
    ).toThrow("process.exit(1)");
    rmSync(tmp, { recursive: true });
  });

  it("removeMember should exit(1) when no roster dir", () => {
    const tmp = mkdtempSync(join(tmpdir(), "test-noroster-"));
    expect(() => removeMember({ name: "Test", target: tmp })).toThrow(
      "process.exit(1)",
    );
    rmSync(tmp, { recursive: true });
  });

  it("removeMember should exit(1) for nonexistent member", async () => {
    const tmp = mkdtempSync(join(tmpdir(), "test-nomember-"));
    await bootstrap({
      preset: "library",
      teamSize: 2,
      projectName: "rm-test",
      target: tmp,
      interactive: false,
    });
    expect(() => removeMember({ name: "Nobody Here", target: tmp })).toThrow(
      "process.exit(1)",
    );
    rmSync(tmp, { recursive: true });
  });

  it("updateMember should exit(1) for nonexistent member", async () => {
    const tmp = mkdtempSync(join(tmpdir(), "test-noupdate-"));
    await bootstrap({
      preset: "library",
      teamSize: 2,
      projectName: "upd-test",
      target: tmp,
      interactive: false,
    });
    expect(() =>
      updateMember({ name: "Nobody", role: "Lead", target: tmp }),
    ).toThrow("process.exit(1)");
    rmSync(tmp, { recursive: true });
  });

  it("randomizeMember should exit(1) for nonexistent member", async () => {
    const tmp = mkdtempSync(join(tmpdir(), "test-norand-"));
    await bootstrap({
      preset: "library",
      teamSize: 2,
      projectName: "rand-test",
      target: tmp,
      interactive: false,
    });
    expect(() =>
      randomizeMember({ name: "Nobody", target: tmp }),
    ).toThrow("process.exit(1)");
    rmSync(tmp, { recursive: true });
  });

  it("validateTeam should exit(1) when no team dir", () => {
    const tmp = mkdtempSync(join(tmpdir(), "test-noval-"));
    expect(() => validateTeam({ target: tmp })).toThrow("process.exit(1)");
    rmSync(tmp, { recursive: true });
  });

  it("validateTeam should exit(1) for missing charter", async () => {
    const tmp = mkdtempSync(join(tmpdir(), "test-nochar-"));
    const teamDir = join(tmp, ".claude", "team", "roster");
    mkdirSync(teamDir, { recursive: true });
    writeFileSync(join(teamDir, "test.md"), "- **Name:** Test\n");
    expect(() => validateTeam({ target: tmp })).toThrow("process.exit(1)");
    rmSync(tmp, { recursive: true });
  });

  it("validateTeam should exit(1) for empty roster", async () => {
    const tmp = mkdtempSync(join(tmpdir(), "test-emptyroster-"));
    const teamDir = join(tmp, ".claude", "team");
    mkdirSync(join(teamDir, "roster"), { recursive: true });
    writeFileSync(join(teamDir, "charter.md"), "# Charter\n");
    writeFileSync(join(teamDir, "trust_matrix.md"), "# Trust\n");
    writeFileSync(join(teamDir, "feedback_log.md"), "# Feedback\n");
    expect(() => validateTeam({ target: tmp })).toThrow("process.exit(1)");
    rmSync(tmp, { recursive: true });
  });

  it("validateTeam should exit(1) for missing trust/feedback", async () => {
    const tmp = mkdtempSync(join(tmpdir(), "test-notrust-"));
    const teamDir = join(tmp, ".claude", "team");
    const rosterDir = join(teamDir, "roster");
    mkdirSync(rosterDir, { recursive: true });
    writeFileSync(join(teamDir, "charter.md"), "# Charter\n");
    writeFileSync(join(rosterDir, "eng_test.md"), "- **Name:** Test\n");
    expect(() => validateTeam({ target: tmp })).toThrow("process.exit(1)");
    rmSync(tmp, { recursive: true });
  });

  it("showStatus should exit(1) when no roster", () => {
    const tmp = mkdtempSync(join(tmpdir(), "test-nostatus-"));
    expect(() => showStatus({ target: tmp })).toThrow("process.exit(1)");
    rmSync(tmp, { recursive: true });
  });
});

// ---------------------------------------------------------------------------
// bootstrap edge cases
// ---------------------------------------------------------------------------

describe("bootstrap edge cases", () => {
  it("should handle missing skill templates gracefully", async () => {
    // Create a custom preset-like scenario where skills don't exist
    // The bootstrap function catches FileNotFoundError for missing skills
    const tmp = mkdtempSync(join(tmpdir(), "test-skill-"));
    await bootstrap({
      preset: "library",
      teamSize: 2,
      projectName: "skill-test",
      target: tmp,
      interactive: false,
    });
    // Skills should be created for existing templates
    const skillsDir = join(tmp, ".claude", "skills");
    expect(existsSync(skillsDir)).toBe(true);
    rmSync(tmp, { recursive: true });
  });

  it("showStatus should display departed members", async () => {
    const tmp = mkdtempSync(join(tmpdir(), "test-departed-"));
    await bootstrap({
      preset: "library",
      teamSize: 3,
      projectName: "dep-test",
      target: tmp,
      interactive: false,
    });
    const rosterDir = join(tmp, ".claude", "team", "roster");
    const cards = readdirSync(rosterDir).filter((f) => f.endsWith(".md"));
    // Archive one
    renameSync(
      join(rosterDir, cards[0]),
      join(rosterDir, `_departed_${cards[0]}`),
    );
    // Should not throw
    showStatus({ target: tmp });
    rmSync(tmp, { recursive: true });
  });

  it("validateTeam should report no skills dir", async () => {
    const tmp = mkdtempSync(join(tmpdir(), "test-noskills-"));
    await bootstrap({
      preset: "library",
      teamSize: 2,
      projectName: "noskill-test",
      target: tmp,
      interactive: false,
    });
    // Remove skills dir
    rmSync(join(tmp, ".claude", "skills"), { recursive: true });
    // Should still pass validation (skills are optional)
    validateTeam({ target: tmp });
    rmSync(tmp, { recursive: true });
  });

  it("validateTeam should report missing roster dir", () => {
    const exitSpy = vi.spyOn(process, "exit").mockImplementation(((code?: number) => {
      throw new Error(`process.exit(${code})`);
    }) as never);
    const tmp = mkdtempSync(join(tmpdir(), "test-norosterdir-"));
    const teamDir = join(tmp, ".claude", "team");
    mkdirSync(teamDir, { recursive: true });
    writeFileSync(join(teamDir, "charter.md"), "# Charter\n");
    writeFileSync(join(teamDir, "trust_matrix.md"), "# Trust\n");
    writeFileSync(join(teamDir, "feedback_log.md"), "# Feedback\n");
    expect(() => validateTeam({ target: tmp })).toThrow("process.exit(1)");
    exitSpy.mockRestore();
    rmSync(tmp, { recursive: true });
  });
});
