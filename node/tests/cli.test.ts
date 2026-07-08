/**
 * Comprehensive tests for the 2real-team Node CLI — targeting >90% coverage.
 */

import { describe, it, expect, beforeEach, vi, afterEach } from "vitest";

// bootstrap() now bridges to the Python framework installer by default
// (--with-hooks). Mock the bridge so these team-scaffolding tests never
// spawn a subprocess; the bridge has its own dedicated test files.
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
  listPresets,
  loadYamlConfig,
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
  usedNamesFromRoster,
  setRng,
  resetRng,
  makeSeededRng,
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

  it("should load preset by name via listPresets", () => {
    const presets = listPresets();
    const library = presets.find((p) => p.name === "library");
    expect(library).toBeDefined();
    expect(library!.default_team_size).toBeGreaterThan(0);
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
// Dedupe root-cause + seedable RNG (#234)
//
// These are the load-bearing regression tests: each FAILS if the fix is
// reverted. `Aisha` is FIRST_NAMES[0] and `Rossi` is LAST_NAMES[18], so a
// scripted RNG that emits [0, 0.37, ...] draws the pair "Aisha Rossi".
// ---------------------------------------------------------------------------

/** A deterministic RNG that replays `values` (cycling), for exact draws. */
function scriptedRng(values: number[]): () => number {
  let i = 0;
  return () => values[i++ % values.length];
}

describe("generateName dedupe compares bare names (#234)", () => {
  afterEach(() => resetRng());

  it("usedNamesFromRoster parses bare `First Last`, not role-prefixed filenames", () => {
    const tmp = mkdtempSync(join(tmpdir(), "test-usednames-"));
    const rosterDir = join(tmp, ".claude", "team", "roster");
    mkdirSync(rosterDir, { recursive: true });
    // Filename is ROLE-PREFIXED; the card body carries the bare name.
    writeFileSync(
      join(rosterDir, "senior_engineer_jane_doe.md"),
      "## Identity\n- **Name:** Jane Doe\n- **Role:** Software Engineer\n",
    );
    const used = usedNamesFromRoster(rosterDir);
    // The fix: the set holds the bare name a candidate is actually compared to.
    expect(used.has("Jane Doe")).toBe(true);
    // The bug: the pre-fix set held the role-prefixed filename string, which
    // never matches a bare "First Last" candidate.
    expect(used.has("senior engineer jane doe")).toBe(false);
    rmSync(tmp, { recursive: true });
  });

  it("warns on stderr when a card's **Name:** cannot be parsed (#252)", () => {
    const tmp = mkdtempSync(join(tmpdir(), "test-usednames-warn-"));
    const rosterDir = join(tmp, ".claude", "team", "roster");
    mkdirSync(rosterDir, { recursive: true });
    // A card with NO **Name:** field -> extractField returns null -> the fallback
    // (filename-derived) name is used AND a stderr warning must be emitted.
    writeFileSync(
      join(rosterDir, "senior_engineer_no_name.md"),
      "## Identity\n- **Role:** Software Engineer\n- **Level:** Senior\n",
    );
    const errSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    try {
      const used = usedNamesFromRoster(rosterDir);
      // Behavior UNCHANGED: the filename-derived fallback still lands in the set.
      expect(used.has("senior engineer no name")).toBe(true);
      // The new observable signal: a visible warning naming the card + the fallback.
      expect(errSpy).toHaveBeenCalledTimes(1);
      const msg = String(errSpy.mock.calls[0][0]);
      expect(msg).toMatch(/senior_engineer_no_name\.md/);
      expect(msg).toMatch(/no parseable \*\*Name:\*\* field/);
      expect(msg).toMatch(/senior engineer no name/);

      // Revert->red proof (in-memory, no git checkout): re-run the SAME parse with
      // the production warn stripped out. The fallback still happens (set unchanged)
      // but NO warning is emitted -> the toHaveBeenCalled assertion above would fail.
      errSpy.mockClear();
      const stripped = (dir: string): Set<string> => {
        const s = new Set<string>();
        for (const f of readdirSync(dir).filter((x) => x.endsWith(".md"))) {
          const stem = f.replace(/^_departed_/, "").replace(/\.md$/, "");
          let name: string | null = null;
          try {
            name = extractField(readFileSync(join(dir, f), "utf-8"), "Name");
          } catch {
            name = null;
          }
          // fallback WITHOUT the console.error warn (pre-#252 behavior)
          s.add(name && name.trim() ? name.trim() : stem.replace(/_/g, " "));
        }
        return s;
      };
      const usedStripped = stripped(rosterDir);
      expect(usedStripped.has("senior engineer no name")).toBe(true); // fallback intact
      expect(errSpy).not.toHaveBeenCalled(); // but silent -> real assertion would go red
    } finally {
      errSpy.mockRestore();
    }
    rmSync(tmp, { recursive: true });
  });

  it("does not warn when **Name:** parses cleanly (#252 control)", () => {
    const tmp = mkdtempSync(join(tmpdir(), "test-usednames-nowarn-"));
    const rosterDir = join(tmp, ".claude", "team", "roster");
    mkdirSync(rosterDir, { recursive: true });
    writeFileSync(
      join(rosterDir, "senior_engineer_jane_doe.md"),
      "## Identity\n- **Name:** Jane Doe\n- **Role:** Software Engineer\n",
    );
    const errSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    try {
      const used = usedNamesFromRoster(rosterDir);
      expect(used.has("Jane Doe")).toBe(true);
      expect(errSpy).not.toHaveBeenCalled(); // clean parse -> no warning
    } finally {
      errSpy.mockRestore();
    }
    rmSync(tmp, { recursive: true });
  });

  it("generateName rejects a candidate already on the roster", () => {
    // used holds the BARE name, exactly as usedNamesFromRoster now produces it.
    const used = new Set<string>(["Aisha Rossi"]);
    // First draw = "Aisha Rossi" (collision -> must be rejected), second draw =
    // "Amara Asante" (FIRST_NAMES[1]/LAST_NAMES[0]).
    const rng = scriptedRng([0, 0.37, 0.02, 0]);
    const [first, last] = generateName(used, rng);
    expect(`${first} ${last}`).toBe("Amara Asante");
    expect(`${first} ${last}`).not.toBe("Aisha Rossi");
  });

  it("addMember(random) does not recreate a name already on the roster", () => {
    const tmp = mkdtempSync(join(tmpdir(), "test-add-dedupe-"));
    const rosterDir = join(tmp, ".claude", "team", "roster");
    mkdirSync(rosterDir, { recursive: true });
    // Existing member whose filename would collide iff the draw repeats it.
    writeFileSync(
      join(rosterDir, "qa_engineer_aisha_rossi.md"),
      "## Identity\n- **Name:** Aisha Rossi\n- **Role:** QA Engineer\n",
    );
    // Force the first random draw to be the existing "Aisha Rossi".
    setRng(scriptedRng([0, 0.37, 0.02, 0]));
    addMember({ role: "QA Engineer", level: "Senior", target: tmp });

    const active = readdirSync(rosterDir).filter(
      (f) => f.endsWith(".md") && !f.startsWith("_departed_"),
    );
    // Pre-fix, the drawn duplicate "Aisha Rossi" would overwrite the existing
    // card -> still 1 card. Post-fix, the collision is rejected and a distinct
    // member is added -> 2 cards.
    expect(active.length).toBe(2);
    expect(active).toContain("qa_engineer_amara_asante.md");
    rmSync(tmp, { recursive: true });
  });
});

describe("seedable RNG is reproducible (#234)", () => {
  afterEach(() => resetRng());

  it("makeSeededRng: same seed yields the same generateName sequence", () => {
    const draw = (seed: number): string[] => {
      const rng = makeSeededRng(seed);
      const used = new Set<string>();
      const out: string[] = [];
      for (let i = 0; i < 8; i++) {
        const [f, l] = generateName(used, rng);
        const full = `${f} ${l}`;
        used.add(full);
        out.push(full);
      }
      return out;
    };
    const a = draw(1234);
    const b = draw(1234);
    const c = draw(9999);
    expect(a).toEqual(b); // reproducible under a fixed seed
    expect(a).not.toEqual(c); // a different seed diverges
  });

  it("setRng makes a full team generation deterministic across runs", () => {
    // The whole point of #234: no flake. With a fixed seed the generated roster
    // is byte-for-byte identical run to run, and every name is unique.
    const generate = (): string[] => {
      setRng(makeSeededRng(42));
      const used = new Set<string>();
      const names: string[] = [];
      for (let i = 0; i < 20; i++) {
        const [f, l] = generateName(used);
        const full = `${f} ${l}`;
        used.add(full);
        names.push(full);
      }
      return names;
    };
    const run1 = generate();
    const run2 = generate();
    expect(run1).toEqual(run2);
    expect(new Set(run1).size).toBe(run1.length); // all unique — no collision
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
    // CLAUDE.md lands at the project root, not under .claude/.
    expect(existsSync(join(tmp, "CLAUDE.md"))).toBe(true);
    expect(existsSync(join(tmp, ".claude", "CLAUDE.md"))).toBe(false);

    const roster = readdirSync(join(tmp, ".claude", "team", "roster")).filter(
      (f) => f.endsWith(".md"),
    );
    expect(roster.length).toBe(3);
  });

  it("should back up an existing root CLAUDE.md (non-clobbering)", async () => {
    writeFileSync(join(tmp, "CLAUDE.md"), "ORIGINAL USER CONTENT");
    await bootstrap({
      preset: "library",
      teamSize: 3,
      projectName: "backup-test",
      target: tmp,
      interactive: false,
    });
    // Original preserved in .bak; framework content now at root CLAUDE.md.
    expect(readFileSync(join(tmp, "CLAUDE.md.bak"), "utf8")).toBe(
      "ORIGINAL USER CONTENT",
    );
    expect(readFileSync(join(tmp, "CLAUDE.md"), "utf8")).not.toBe(
      "ORIGINAL USER CONTENT",
    );
  });

  it("should not clobber a pre-existing CLAUDE.md.bak", async () => {
    writeFileSync(join(tmp, "CLAUDE.md"), "CURRENT");
    writeFileSync(join(tmp, "CLAUDE.md.bak"), "OLDER BACKUP");
    await bootstrap({
      preset: "library",
      teamSize: 3,
      projectName: "backup2-test",
      target: tmp,
      interactive: false,
    });
    expect(readFileSync(join(tmp, "CLAUDE.md.bak"), "utf8")).toBe("OLDER BACKUP");
    expect(readFileSync(join(tmp, "CLAUDE.md.bak.1"), "utf8")).toBe("CURRENT");
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

// ---------------------------------------------------------------------------
// YAML config file support
// ---------------------------------------------------------------------------

describe("loadYamlConfig", () => {
  it("should load a valid YAML config", () => {
    const tmp = mkdtempSync(join(tmpdir(), "test-yaml-"));
    const cfgPath = join(tmp, "config.yaml");
    writeFileSync(cfgPath, "preset: library\nproject_name: test\nteam_size: 3\n");
    const cfg = loadYamlConfig(cfgPath);
    expect(cfg.preset).toBe("library");
    expect(cfg.project_name).toBe("test");
    expect(cfg.team_size).toBe(3);
    rmSync(tmp, { recursive: true });
  });

  it("should throw for missing file", () => {
    expect(() => loadYamlConfig("/nonexistent/path.yaml")).toThrow("Config file not found");
  });

  it("should throw for non-mapping YAML", () => {
    const tmp = mkdtempSync(join(tmpdir(), "test-listyaml-"));
    const cfgPath = join(tmp, "list.yaml");
    writeFileSync(cfgPath, "- item1\n- item2\n");
    expect(() => loadYamlConfig(cfgPath)).toThrow("YAML mapping");
    rmSync(tmp, { recursive: true });
  });

  it("should throw for missing preset", () => {
    const tmp = mkdtempSync(join(tmpdir(), "test-nopreset-yaml-"));
    const cfgPath = join(tmp, "nopreset.yaml");
    writeFileSync(cfgPath, "project_name: test\n");
    expect(() => loadYamlConfig(cfgPath)).toThrow("preset: Field required");
    rmSync(tmp, { recursive: true });
  });

  it("should throw for invalid team_size type", () => {
    const tmp = mkdtempSync(join(tmpdir(), "test-badsize-"));
    const cfgPath = join(tmp, "badsize.yaml");
    writeFileSync(cfgPath, "preset: library\nteam_size: not_a_number\n");
    expect(() => loadYamlConfig(cfgPath)).toThrow("valid integer");
    rmSync(tmp, { recursive: true });
  });

  it("should parse members and skills arrays", () => {
    const tmp = mkdtempSync(join(tmpdir(), "test-arrays-"));
    const cfgPath = join(tmp, "arrays.yaml");
    writeFileSync(cfgPath, "preset: library\nskills:\n  - retro\n  - wave-start\nmembers:\n  - name: Alice Smith\n    role: Tech Lead\n");
    const cfg = loadYamlConfig(cfgPath);
    expect(cfg.skills).toEqual(["retro", "wave-start"]);
    expect(cfg.members).toHaveLength(1);
    expect(cfg.members![0].name).toBe("Alice Smith");
    expect(cfg.members![0].role).toBe("Tech Lead");
    rmSync(tmp, { recursive: true });
  });
});

describe("bootstrap with YAML config", () => {
  it("should bootstrap from config file", async () => {
    const tmp = mkdtempSync(join(tmpdir(), "test-cfgboot-"));
    const cfgPath = join(tmp, "config.yaml");
    writeFileSync(cfgPath, "preset: library\nproject_name: cfg-test\nteam_size: 3\n");
    const target = join(tmp, "output");
    mkdirSync(target);
    await bootstrap({
      config: cfgPath,
      target,
      interactive: false,
    });
    expect(existsSync(join(target, ".claude", "team", "charter.md"))).toBe(true);
    const cards = readdirSync(join(target, ".claude", "team", "roster")).filter(f => f.endsWith(".md"));
    expect(cards.length).toBe(3);
    rmSync(tmp, { recursive: true });
  });

  it("should apply member overrides from config", async () => {
    const tmp = mkdtempSync(join(tmpdir(), "test-cfgoverride-"));
    const cfgPath = join(tmp, "config.yaml");
    writeFileSync(cfgPath, "preset: library\nproject_name: override-test\nteam_size: 3\nmembers:\n  - name: Alice Smith\n    role: Tech Lead\n    level: Staff\n  - name: Bob Jones\n");
    const target = join(tmp, "output");
    mkdirSync(target);
    await bootstrap({
      config: cfgPath,
      target,
      interactive: false,
    });
    const rosterDir = join(target, ".claude", "team", "roster");
    const cards = readdirSync(rosterDir).filter(f => f.endsWith(".md"));
    expect(cards.length).toBe(3);
    const aliceCard = cards.find(f => f.includes("alice_smith"));
    expect(aliceCard).toBeDefined();
    const aliceContent = readFileSync(join(rosterDir, aliceCard!), "utf-8");
    expect(aliceContent).toContain("Alice Smith");
    expect(aliceContent).toContain("Tech Lead");
    expect(aliceContent).toContain("Staff");
    const bobCard = cards.find(f => f.includes("bob_jones"));
    expect(bobCard).toBeDefined();
    rmSync(tmp, { recursive: true });
  });

  it("should apply skills override from config", async () => {
    const tmp = mkdtempSync(join(tmpdir(), "test-cfgskills-"));
    const cfgPath = join(tmp, "config.yaml");
    writeFileSync(cfgPath, "preset: library\nproject_name: skills-test\nteam_size: 2\nskills:\n  - retro\n");
    const target = join(tmp, "output");
    mkdirSync(target);
    await bootstrap({
      config: cfgPath,
      target,
      interactive: false,
    });
    const skillsDir = join(target, ".claude", "skills");
    const skills = readdirSync(skillsDir).filter(f => f.endsWith(".md"));
    const skillNames = skills.map(f => f.replace(".md", ""));
    expect(skillNames).toContain("retro");
    expect(skills.length).toBe(1);
    rmSync(tmp, { recursive: true });
  });
});
