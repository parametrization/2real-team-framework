/**
 * Core bootstrap logic for Node CLI.
 */

import { readFileSync, mkdirSync, writeFileSync, existsSync, readdirSync, renameSync } from "node:fs";
import { resolve, join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { renderTemplate, renderSkill } from "./templates.js";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const PRESETS_DIR = resolve(__dirname, "../../presets");

interface BootstrapOptions {
  preset?: string;
  teamSize?: number;
  config?: string;
  projectName?: string;
  target: string;
  interactive: boolean;
}

interface PresetRole {
  role: string;
  level: string;
  count: number;
  required: boolean;
}

interface Preset {
  name: string;
  description: string;
  default_team_size: number;
  roles: PresetRole[];
  skills: string[];
  default_ci: string;
}

export interface TeamMember {
  name: string;
  role: string;
  level: string;
  email: string;
  reports_to: string;
  personality: string;
}

// Name pools — match Python pools exactly
export const FIRST_NAMES = [
  "Aisha", "Amara", "Andrei", "Bj\u00f6rk", "Carolina", "Chen", "Dmitri",
  "Elena", "Fatima", "Hiro", "Ibrahim", "Jada", "Kai", "Kwame", "Lena",
  "Mei-Lin", "Nadia", "Omar", "Priya", "Ravi", "Renaud", "Sakura",
  "Sunita", "Tariq", "Tomasz", "Yara", "Zara", "Alejandro", "Beatriz",
  "Ciro", "Dalia", "Elio", "Femi", "Greta", "Hugo", "Ingrid", "Jun",
  "Kofi", "Lila", "Marco", "Nia", "Oscar", "Paloma", "Qasim", "Rosa",
  "Sven", "Tara", "Umar", "Vera", "Wei", "Xena", "Yuki", "Zuri",
];

export const LAST_NAMES = [
  "Asante", "Al-Rashidi", "Bianchi", "Chang", "Diallo", "Eriksson",
  "Fern\u00e1ndez", "Garc\u00eda", "Hadid", "Inoue", "Jensen", "Krishnamurthy",
  "L\u00f3pez", "M\u00e9ndez-R\u00edos", "Nakamura", "Okonkwo", "Petrova", "Qureshi",
  "Rossi", "Singh", "Tanaka", "Ueda", "Volkov", "W\u00f3jcik", "Xu",
  "Yamamoto", "Zhang", "Abubakar", "Bjornsson", "Costa", "Devi",
  "El-Amin", "Fischer", "Gupta", "Hassan", "Ito", "Johansson", "Kim",
  "Li", "Morales", "Nair", "Osei", "Park", "Rahman", "Sato",
  "Tremblay", "Uchida", "Vargas", "Wang", "Yamada", "Zhao",
];

export const COMMUNICATION_STYLES = [
  "Direct and structured. Prefers bullet points and numbered lists over prose.",
  "Deliberate and thorough. Reads the entire thread before responding.",
  "Enthusiastic and collaborative. Brings energy to discussions.",
  "Analytical and precise. Favors data-driven decisions.",
  "Pragmatic and concise. Focuses on what needs to get done.",
  "Thoughtful and empathetic. Considers team dynamics in every decision.",
  "Crisp and action-oriented. Every message ends with a clear next step.",
  "Measured and diplomatic. Navigates disagreements with tact.",
];

function randomChoice<T>(arr: T[]): T {
  return arr[Math.floor(Math.random() * arr.length)];
}

export function generateName(used: Set<string>): [string, string] {
  for (let i = 0; i < 100; i++) {
    const first = randomChoice(FIRST_NAMES);
    const last = randomChoice(LAST_NAMES);
    const full = `${first} ${last}`;
    if (!used.has(full)) return [first, last];
  }
  throw new Error("Could not generate unique name");
}

export function makeEmail(first: string, last: string, prefix: string = ""): string {
  const clean = (s: string) => s.normalize("NFD").replace(/[\u0300-\u036f]/g, "");
  if (prefix) {
    return `${prefix}+${clean(first)}.${clean(last)}@gmail.com`;
  }
  return `${clean(first)}.${clean(last)}@gmail.com`;
}

export function extractField(content: string, field: string): string | null {
  for (const line of content.split("\n")) {
    if (line.includes(`**${field}:**`)) {
      return line.split(`**${field}:**`)[1]?.trim() ?? null;
    }
  }
  return null;
}

export function replaceField(content: string, field: string, value: string): string {
  const lines = content.split("\n");
  for (let i = 0; i < lines.length; i++) {
    if (lines[i].includes(`**${field}:**`)) {
      const prefix = lines[i].split(`**${field}:**`)[0];
      lines[i] = `${prefix}**${field}:** ${value}`;
      break;
    }
  }
  return lines.join("\n");
}

export function safeName(name: string): string {
  return name.toLowerCase().replace(/ /g, "_").replace(/-/g, "_");
}

export function findRosterCards(rosterDir: string, name: string): string[] {
  if (!existsSync(rosterDir)) return [];
  const safe = safeName(name);
  return readdirSync(rosterDir)
    .filter((f) => f.endsWith(".md") && f.includes(safe) && !f.startsWith("_departed_"));
}

export function loadPreset(name: string): Preset {
  const path = join(PRESETS_DIR, `${name}.json`);
  if (!existsSync(path)) {
    throw new Error(`Unknown preset: ${name}`);
  }
  return JSON.parse(readFileSync(path, "utf-8"));
}

export function listPresets(): Preset[] {
  if (!existsSync(PRESETS_DIR)) return [];
  return readdirSync(PRESETS_DIR)
    .filter((f) => f.endsWith(".json"))
    .map((f) => JSON.parse(readFileSync(join(PRESETS_DIR, f), "utf-8")) as Preset);
}

export async function bootstrap(opts: BootstrapOptions): Promise<void> {
  const target = resolve(opts.target);
  let presetName = opts.preset;

  if (!presetName) {
    if (opts.interactive) {
      const inquirer = await import("inquirer");
      const { preset } = await inquirer.default.prompt([
        {
          type: "list",
          name: "preset",
          message: "Choose a preset:",
          choices: ["fullstack-monorepo", "data-pipeline", "library"],
        },
      ]);
      presetName = preset;
    } else {
      console.error("Error: --preset is required in non-interactive mode");
      process.exit(1);
    }
  }

  const preset = loadPreset(presetName!);

  let projectName = opts.projectName;
  if (!projectName && opts.interactive) {
    const inquirer = await import("inquirer");
    const { name } = await inquirer.default.prompt([
      {
        type: "input",
        name: "name",
        message: "Project name:",
        default: target.split("/").pop() ?? "my-project",
      },
    ]);
    projectName = name;
  } else if (!projectName) {
    projectName = target.split("/").pop() ?? "my-project";
  }

  let teamSize = opts.teamSize;
  if (!teamSize && opts.interactive) {
    const inquirer = await import("inquirer");
    const { size } = await inquirer.default.prompt([
      {
        type: "number",
        name: "size",
        message: "Team size:",
        default: preset.default_team_size,
      },
    ]);
    teamSize = size;
  }
  if (!teamSize) {
    teamSize = preset.default_team_size;
  }

  // Generate team
  const used = new Set<string>();
  const members: TeamMember[] = [];

  for (const role of preset.roles) {
    if (!role.required) continue;
    for (let i = 0; i < role.count && members.length < teamSize; i++) {
      const [first, last] = generateName(used);
      used.add(`${first} ${last}`);
      members.push({
        name: `${first} ${last}`,
        role: role.role,
        level: role.level,
        email: makeEmail(first, last),
        reports_to: "",
        personality: randomChoice(COMMUNICATION_STYLES),
      });
    }
  }

  for (const role of preset.roles) {
    if (role.required) continue;
    for (let i = 0; i < role.count && members.length < teamSize; i++) {
      const [first, last] = generateName(used);
      used.add(`${first} ${last}`);
      members.push({
        name: `${first} ${last}`,
        role: role.role,
        level: role.level,
        email: makeEmail(first, last),
        reports_to: "",
        personality: randomChoice(COMMUNICATION_STYLES),
      });
    }
  }

  const context = { project_name: projectName, team_members: members };

  // Create directories
  const teamDir = join(target, ".claude", "team");
  const rosterDir = join(teamDir, "roster");
  const skillsDir = join(target, ".claude", "skills");
  mkdirSync(rosterDir, { recursive: true });
  mkdirSync(skillsDir, { recursive: true });

  const created: string[] = [];

  // Charter
  const charter = renderTemplate("charter.md.mustache", context);
  writeFileSync(join(teamDir, "charter.md"), charter);
  created.push(".claude/team/charter.md");

  // Roster cards
  for (const m of members) {
    const card = renderTemplate("roster-card.md.mustache", m as unknown as Record<string, unknown>);
    const safe = safeName(m.name);
    const rolePrefix = m.role.toLowerCase().replace(/ /g, "_");
    const cardPath = join(rosterDir, `${rolePrefix}_${safe}.md`);
    writeFileSync(cardPath, card);
    created.push(`.claude/team/roster/${rolePrefix}_${safe}.md`);
  }

  // Trust matrix
  const trust = renderTemplate("trust-matrix.md.mustache", context);
  writeFileSync(join(teamDir, "trust_matrix.md"), trust);
  created.push(".claude/team/trust_matrix.md");

  // Feedback log
  const feedback = renderTemplate("feedback-log.md.mustache", context);
  writeFileSync(join(teamDir, "feedback_log.md"), feedback);
  created.push(".claude/team/feedback_log.md");

  // CLAUDE.md
  const claudeMd = renderTemplate("CLAUDE.md.mustache", context);
  writeFileSync(join(target, ".claude", "CLAUDE.md"), claudeMd);
  created.push(".claude/CLAUDE.md");

  // Skills
  for (const skill of preset.skills) {
    try {
      const rendered = renderSkill(`${skill}.md.mustache`, context);
      if (rendered) {
        writeFileSync(join(skillsDir, `${skill}.md`), rendered);
        created.push(`.claude/skills/${skill}.md`);
      }
    } catch {
      // Skip missing skill templates
    }
  }

  console.log(`\nCreated ${created.length} files:`);
  for (const f of created) {
    console.log(`  ${f}`);
  }
  console.log(`\nTeam framework bootstrapped for '${projectName}'!`);
}

export function addMember(opts: {
  name?: string;
  role: string;
  level: string;
  target: string;
}): void {
  const target = resolve(opts.target);
  const rosterDir = join(target, ".claude", "team", "roster");

  if (!existsSync(rosterDir)) {
    console.error("Error: No roster directory found. Run `2real-team init` first.");
    process.exit(1);
  }

  let name = opts.name;
  let first: string, last: string;

  if (!name) {
    const used = new Set(
      readdirSync(rosterDir)
        .filter((f) => f.endsWith(".md"))
        .map((f) => f.replace(/_/g, " ").replace(".md", ""))
    );
    [first, last] = generateName(used);
    name = `${first} ${last}`;
  } else {
    const parts = name.split(" ", 2);
    first = parts[0];
    last = parts[1] ?? "";
  }

  const email = makeEmail(first!, last!);

  const context = {
    name,
    role: opts.role,
    level: opts.level,
    email,
    personality: "To be defined.",
  };

  const card = renderTemplate("roster-card.md.mustache", context);
  const safe = safeName(name);
  const rolePrefix = opts.role.toLowerCase().replace(/ /g, "_");
  const cardPath = join(rosterDir, `${rolePrefix}_${safe}.md`);
  writeFileSync(cardPath, card);

  console.log(`Added: ${name} (${opts.role}, ${opts.level}) -> ${cardPath}`);
}

export function removeMember(opts: { name: string; target: string }): void {
  const target = resolve(opts.target);
  const rosterDir = join(target, ".claude", "team", "roster");

  if (!existsSync(rosterDir)) {
    console.error("Error: No roster directory found.");
    process.exit(1);
  }

  const matches = findRosterCards(rosterDir, opts.name);

  if (matches.length === 0) {
    console.error(`Error: No active roster card found for '${opts.name}'`);
    process.exit(1);
  }

  for (const match of matches) {
    const oldPath = join(rosterDir, match);
    const newPath = join(rosterDir, `_departed_${match}`);
    renameSync(oldPath, newPath);
    console.log(`Archived: ${match} -> _departed_${match}`);
  }
}

export function updateMember(opts: {
  name: string;
  role?: string;
  level?: string;
  target: string;
}): void {
  const target = resolve(opts.target);
  const rosterDir = join(target, ".claude", "team", "roster");

  const matches = findRosterCards(rosterDir, opts.name);

  if (matches.length === 0) {
    console.error(`Error: No active roster card found for '${opts.name}'`);
    process.exit(1);
  }

  const cardPath = join(rosterDir, matches[0]);
  let content = readFileSync(cardPath, "utf-8");

  if (opts.role) {
    content = replaceField(content, "Role", opts.role);
  }
  if (opts.level) {
    content = replaceField(content, "Level", opts.level);
  }

  writeFileSync(cardPath, content);
  console.log(`Updated: ${opts.name}`);
}

export function randomizeMember(opts: { name: string; target: string }): void {
  const target = resolve(opts.target);
  const rosterDir = join(target, ".claude", "team", "roster");

  const matches = findRosterCards(rosterDir, opts.name);

  if (matches.length === 0) {
    console.error(`Error: No active roster card found for '${opts.name}'`);
    process.exit(1);
  }

  const oldFile = matches[0];
  const oldPath = join(rosterDir, oldFile);
  const content = readFileSync(oldPath, "utf-8");

  // Extract role and level from existing card
  const role = extractField(content, "Role") ?? "Software Engineer";
  const level = extractField(content, "Level") ?? "Senior";

  // Archive old
  const archivedPath = join(rosterDir, `_departed_${oldFile}`);
  renameSync(oldPath, archivedPath);

  // Generate new identity
  const used = new Set(
    readdirSync(rosterDir)
      .filter((f) => f.endsWith(".md") && !f.startsWith("_departed_"))
      .map((f) => f.replace(/_/g, " ").replace(".md", ""))
  );
  const [first, last] = generateName(used);
  const newName = `${first} ${last}`;
  const email = makeEmail(first, last);

  const context = {
    name: newName,
    role,
    level,
    email,
    personality: randomChoice(COMMUNICATION_STYLES),
  };

  const card = renderTemplate("roster-card.md.mustache", context);
  const newSafe = safeName(newName);
  const rolePrefix = role.toLowerCase().replace(/ /g, "_");
  const newPath = join(rosterDir, `${rolePrefix}_${newSafe}.md`);
  writeFileSync(newPath, card);

  console.log(`Archived: ${oldFile} -> _departed_${oldFile}`);
  console.log(`Created: ${newName} (${role}, ${level}) -> ${rolePrefix}_${newSafe}.md`);
}

export function validateTeam(opts: { target: string }): void {
  const target = resolve(opts.target);
  const teamDir = join(target, ".claude", "team");
  const skillsDir = join(target, ".claude", "skills");
  const errors: string[] = [];

  if (!existsSync(teamDir)) {
    console.error("Error: No .claude/team/ directory found. Run `2real-team init` first.");
    process.exit(1);
  }

  // Check charter
  if (!existsSync(join(teamDir, "charter.md"))) {
    errors.push("Missing charter.md");
  }

  // Check roster
  const rosterDir = join(teamDir, "roster");
  if (!existsSync(rosterDir)) {
    errors.push("Missing roster/ directory");
  } else {
    const active = readdirSync(rosterDir)
      .filter((f) => f.endsWith(".md") && !f.startsWith("_departed_"));
    if (active.length === 0) {
      errors.push("No active roster cards found");
    } else {
      console.log(`Found ${active.length} active team members`);
    }
  }

  // Check trust matrix
  if (!existsSync(join(teamDir, "trust_matrix.md"))) {
    errors.push("Missing trust_matrix.md");
  }

  // Check feedback log
  if (!existsSync(join(teamDir, "feedback_log.md"))) {
    errors.push("Missing feedback_log.md");
  }

  // Check skills
  if (existsSync(skillsDir)) {
    const skills = readdirSync(skillsDir).filter((f) => f.endsWith(".md"));
    console.log(`Found ${skills.length} skills`);
  } else {
    console.log("No skills directory found");
  }

  if (errors.length > 0) {
    console.error(`\nValidation failed with ${errors.length} error(s):`);
    for (const e of errors) {
      console.error(`  x ${e}`);
    }
    process.exit(1);
  } else {
    console.log("\nValidation passed!");
  }
}

export function showStatus(opts: { target: string }): void {
  const target = resolve(opts.target);
  const rosterDir = join(target, ".claude", "team", "roster");

  if (!existsSync(rosterDir)) {
    console.error("No team found. Run `2real-team init` first.");
    process.exit(1);
  }

  const files = readdirSync(rosterDir).filter((f) => f.endsWith(".md")).sort();

  // Calculate column widths
  const rows: { name: string; role: string; level: string; status: string }[] = [];
  for (const file of files) {
    const content = readFileSync(join(rosterDir, file), "utf-8");
    const name = extractField(content, "Name") ?? file.replace(".md", "");
    const role = extractField(content, "Role") ?? "?";
    const level = extractField(content, "Level") ?? "?";
    const isDeparted = file.startsWith("_departed_");
    rows.push({ name, role, level, status: isDeparted ? "Archived" : "Active" });
  }

  // Print table
  const nameW = Math.max(4, ...rows.map((r) => r.name.length));
  const roleW = Math.max(4, ...rows.map((r) => r.role.length));
  const levelW = Math.max(5, ...rows.map((r) => r.level.length));
  const statusW = Math.max(6, ...rows.map((r) => r.status.length));

  console.log("\nTeam Roster");
  console.log(
    `${"Name".padEnd(nameW)}  ${"Role".padEnd(roleW)}  ${"Level".padEnd(levelW)}  ${"Status".padEnd(statusW)}`
  );
  console.log(`${"-".repeat(nameW)}  ${"-".repeat(roleW)}  ${"-".repeat(levelW)}  ${"-".repeat(statusW)}`);
  for (const r of rows) {
    console.log(
      `${r.name.padEnd(nameW)}  ${r.role.padEnd(roleW)}  ${r.level.padEnd(levelW)}  ${r.status.padEnd(statusW)}`
    );
  }

  // Count skills
  const skillsDir = join(target, ".claude", "skills");
  if (existsSync(skillsDir)) {
    const skillCount = readdirSync(skillsDir).filter((f) => f.endsWith(".md")).length;
    console.log(`\nSkills installed: ${skillCount}`);
  }
}
