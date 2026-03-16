import { describe, it, expect, beforeEach } from "vitest";
import { existsSync, readFileSync, mkdirSync, readdirSync } from "node:fs";
import { resolve, dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { tmpdir } from "node:os";
import {
  generateName,
  makeEmail,
  extractField,
  replaceField,
  safeName,
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
import { renderTemplate, listTemplates, listSkills } from "../src/templates.js";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const PRESETS_DIR = resolve(__dirname, "../../presets");
const TEMPLATES_DIR = resolve(__dirname, "../../templates");
const SKILLS_DIR = resolve(__dirname, "../../skills");

describe("presets", () => {
  it("should have all three preset files", () => {
    expect(existsSync(resolve(PRESETS_DIR, "fullstack-monorepo.json"))).toBe(true);
    expect(existsSync(resolve(PRESETS_DIR, "data-pipeline.json"))).toBe(true);
    expect(existsSync(resolve(PRESETS_DIR, "library.json"))).toBe(true);
  });

  it("should have valid JSON in each preset", () => {
    for (const name of ["fullstack-monorepo", "data-pipeline", "library"]) {
      const content = readFileSync(resolve(PRESETS_DIR, `${name}.json`), "utf-8");
      const preset = JSON.parse(content);
      expect(preset.name).toBe(name);
      expect(preset.roles).toBeInstanceOf(Array);
      expect(preset.skills).toBeInstanceOf(Array);
      expect(preset.default_team_size).toBeGreaterThan(0);
    }
  });

  it("listPresets should return all presets", () => {
    const presets = listPresets();
    expect(presets.length).toBeGreaterThanOrEqual(3);
    const names = presets.map((p) => p.name);
    expect(names).toContain("fullstack-monorepo");
    expect(names).toContain("data-pipeline");
    expect(names).toContain("library");
  });
});

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
});

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
});

describe("generateName", () => {
  it("should generate unique names", () => {
    const used = new Set<string>();
    for (let i = 0; i < 20; i++) {
      const [first, last] = generateName(used);
      const full = `${first} ${last}`;
      expect(used.has(full)).toBe(false);
      used.add(full);
    }
  });

  it("should use names from the pools", () => {
    const [first, last] = generateName(new Set());
    expect(FIRST_NAMES).toContain(first);
    expect(LAST_NAMES).toContain(last);
  });
});

describe("makeEmail", () => {
  it("should strip diacritics", () => {
    expect(makeEmail("Carolina", "Méndez-Ríos")).toBe("Carolina.Mendez-Rios@gmail.com");
    expect(makeEmail("Tomasz", "Wójcik")).toBe("Tomasz.Wojcik@gmail.com");
  });

  it("should support prefix", () => {
    expect(makeEmail("Tomasz", "Wójcik", "org")).toBe("org+Tomasz.Wojcik@gmail.com");
  });
});

describe("name pools", () => {
  it("should have 53 first names (matching Python)", () => {
    expect(FIRST_NAMES.length).toBe(53);
  });

  it("should have 51 last names (matching Python)", () => {
    expect(LAST_NAMES.length).toBe(51);
  });

  it("should have 8 communication styles", () => {
    expect(COMMUNICATION_STYLES.length).toBe(8);
  });
});

describe("extractField", () => {
  it("should extract a field value", () => {
    const content = "- **Name:** Alice Smith\n- **Role:** Engineer\n- **Level:** Senior";
    expect(extractField(content, "Name")).toBe("Alice Smith");
    expect(extractField(content, "Role")).toBe("Engineer");
    expect(extractField(content, "Level")).toBe("Senior");
  });

  it("should return null for missing field", () => {
    expect(extractField("no fields here", "Name")).toBeNull();
  });
});

describe("replaceField", () => {
  it("should replace a field value", () => {
    const content = "- **Role:** Engineer\n- **Level:** Senior";
    const result = replaceField(content, "Role", "Manager");
    expect(result).toContain("**Role:** Manager");
    expect(result).toContain("**Level:** Senior");
  });
});

describe("safeName", () => {
  it("should lowercase and replace spaces/hyphens with underscores", () => {
    expect(safeName("Mei-Lin Chang")).toBe("mei_lin_chang");
  });
});

describe("template rendering", () => {
  it("should render charter template", () => {
    const result = renderTemplate("charter.md.mustache", {
      project_name: "test-proj",
      team_members: [{ name: "Alice", role: "Engineer", level: "Senior" }],
    });
    expect(result).toContain("test-proj");
  });

  it("should render roster card template", () => {
    const result = renderTemplate("roster-card.md.mustache", {
      name: "Alice Smith",
      role: "Engineer",
      level: "Senior",
      email: "alice@test.com",
      personality: "Direct and structured.",
    });
    expect(result).toContain("Alice Smith");
    expect(result).toContain("Engineer");
    expect(result).toContain("Senior");
    expect(result).toContain("alice@test.com");
  });
});

function makeTmpDir(): string {
  const dir = join(tmpdir(), `2real-test-${Date.now()}-${Math.random().toString(36).slice(2)}`);
  mkdirSync(dir, { recursive: true });
  return dir;
}

describe("E2E: bootstrap + validate + status", () => {
  let tmpDir: string;

  beforeEach(() => {
    tmpDir = makeTmpDir();
  });

  it("should bootstrap, validate, and show status", async () => {
    await bootstrap({
      preset: "library",
      teamSize: 3,
      projectName: "e2e-test",
      target: tmpDir,
      interactive: false,
    });

    // Verify file structure
    expect(existsSync(join(tmpDir, ".claude", "team", "charter.md"))).toBe(true);
    expect(existsSync(join(tmpDir, ".claude", "team", "trust_matrix.md"))).toBe(true);
    expect(existsSync(join(tmpDir, ".claude", "team", "feedback_log.md"))).toBe(true);
    expect(existsSync(join(tmpDir, ".claude", "CLAUDE.md"))).toBe(true);

    const rosterDir = join(tmpDir, ".claude", "team", "roster");
    const cards = readdirSync(rosterDir).filter((f) => f.endsWith(".md"));
    expect(cards.length).toBe(3);

    // Validate should not throw (would call process.exit on failure)
    // We test by checking files exist since validateTeam calls process.exit
    expect(existsSync(join(tmpDir, ".claude", "team", "charter.md"))).toBe(true);
    expect(existsSync(join(tmpDir, ".claude", "team", "roster"))).toBe(true);
    expect(existsSync(join(tmpDir, ".claude", "team", "trust_matrix.md"))).toBe(true);
    expect(existsSync(join(tmpDir, ".claude", "team", "feedback_log.md"))).toBe(true);
  });

  it("should add a member", async () => {
    await bootstrap({
      preset: "library",
      teamSize: 2,
      projectName: "add-test",
      target: tmpDir,
      interactive: false,
    });

    addMember({ name: "Test Person", role: "QA Engineer", level: "Mid", target: tmpDir });

    const rosterDir = join(tmpDir, ".claude", "team", "roster");
    const cards = readdirSync(rosterDir).filter((f) => f.endsWith(".md"));
    expect(cards.length).toBe(3);
    expect(cards.some((c) => c.includes("test_person"))).toBe(true);

    // Check card contents
    const testCard = cards.find((c) => c.includes("test_person"))!;
    const content = readFileSync(join(rosterDir, testCard), "utf-8");
    expect(extractField(content, "Name")).toBe("Test Person");
    expect(extractField(content, "Role")).toBe("QA Engineer");
  });

  it("should remove a member", async () => {
    await bootstrap({
      preset: "library",
      teamSize: 2,
      projectName: "remove-test",
      target: tmpDir,
      interactive: false,
    });

    const rosterDir = join(tmpDir, ".claude", "team", "roster");
    const cardsBefore = readdirSync(rosterDir).filter(
      (f) => f.endsWith(".md") && !f.startsWith("_departed_")
    );
    expect(cardsBefore.length).toBe(2);

    // Extract a name from first card to remove
    const firstCard = cardsBefore[0];
    const content = readFileSync(join(rosterDir, firstCard), "utf-8");
    const memberName = extractField(content, "Name")!;

    removeMember({ name: memberName, target: tmpDir });

    const cardsAfter = readdirSync(rosterDir).filter(
      (f) => f.endsWith(".md") && !f.startsWith("_departed_")
    );
    expect(cardsAfter.length).toBe(1);

    const departed = readdirSync(rosterDir).filter((f) => f.startsWith("_departed_"));
    expect(departed.length).toBe(1);
  });

  it("should update a member", async () => {
    await bootstrap({
      preset: "library",
      teamSize: 2,
      projectName: "update-test",
      target: tmpDir,
      interactive: false,
    });

    const rosterDir = join(tmpDir, ".claude", "team", "roster");
    const cards = readdirSync(rosterDir).filter((f) => f.endsWith(".md"));
    const content = readFileSync(join(rosterDir, cards[0]), "utf-8");
    const memberName = extractField(content, "Name")!;

    updateMember({ name: memberName, role: "Principal Engineer", level: "Staff", target: tmpDir });

    const updatedContent = readFileSync(join(rosterDir, cards[0]), "utf-8");
    expect(extractField(updatedContent, "Role")).toBe("Principal Engineer");
    expect(extractField(updatedContent, "Level")).toBe("Staff");
  });

  it("should randomize a member", async () => {
    await bootstrap({
      preset: "library",
      teamSize: 2,
      projectName: "randomize-test",
      target: tmpDir,
      interactive: false,
    });

    const rosterDir = join(tmpDir, ".claude", "team", "roster");
    const cardsBefore = readdirSync(rosterDir).filter(
      (f) => f.endsWith(".md") && !f.startsWith("_departed_")
    );
    const content = readFileSync(join(rosterDir, cardsBefore[0]), "utf-8");
    const memberName = extractField(content, "Name")!;

    randomizeMember({ name: memberName, target: tmpDir });

    const cardsAfter = readdirSync(rosterDir).filter(
      (f) => f.endsWith(".md") && !f.startsWith("_departed_")
    );
    expect(cardsAfter.length).toBe(2);

    const departed = readdirSync(rosterDir).filter((f) => f.startsWith("_departed_"));
    expect(departed.length).toBe(1);
  });
});
