import { describe, it, expect } from "vitest";
import { existsSync, readFileSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

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
