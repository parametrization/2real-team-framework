/**
 * Core bootstrap logic for Node CLI.
 */

import { readFileSync, mkdirSync, writeFileSync, existsSync, readdirSync, renameSync } from "node:fs";
import { resolve, join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import Mustache from "mustache";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

/**
 * Resolve a shared data directory.  Checks the package-local copy first
 * (npm install), then the repo-root relative path (development).
 */
function resolveDataDir(name: string): string {
  // When installed as an npm package: dist/ -> ../{name}
  const pkg = resolve(__dirname, "..", name);
  if (existsSync(pkg)) return pkg;
  // Development: src/ or dist/ -> ../../{name} (repo root)
  return resolve(__dirname, "../..", name);
}

const TEMPLATES_DIR = resolveDataDir("templates");
const PRESETS_DIR = resolveDataDir("presets");
const SKILLS_DIR = resolveDataDir("skills");

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

interface TeamMember {
  name: string;
  agent_name: string;
  role: string;
  level: string;
  email: string;
  reports_to: string;
  personality: string;
}

function toAgentName(name: string): string {
  return name.toLowerCase().replace(/ /g, "-");
}

// Name pools — match Python pools exactly
export const FIRST_NAMES = [
  "Aisha", "Amara", "Andrei", "Björk", "Carolina", "Chen", "Dmitri",
  "Elena", "Fatima", "Hiro", "Ibrahim", "Jada", "Kai", "Kwame", "Lena",
  "Mei-Lin", "Nadia", "Omar", "Priya", "Ravi", "Renaud", "Sakura",
  "Sunita", "Tariq", "Tomasz", "Yara", "Zara", "Alejandro", "Beatriz",
  "Ciro", "Dalia", "Elio", "Femi", "Greta", "Hugo", "Ingrid", "Jun",
  "Kofi", "Lila", "Marco", "Nia", "Oscar", "Paloma", "Qasim", "Rosa",
  "Sven", "Tara", "Umar", "Vera", "Wei", "Xena", "Yuki", "Zuri",
];

export const LAST_NAMES = [
  "Asante", "Al-Rashidi", "Bianchi", "Chang", "Diallo", "Eriksson",
  "Fernández", "García", "Hadid", "Inoue", "Jensen", "Krishnamurthy",
  "López", "Méndez-Ríos", "Nakamura", "Okonkwo", "Petrova", "Qureshi",
  "Rossi", "Singh", "Tanaka", "Ueda", "Volkov", "Wójcik", "Xu",
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

function renderTemplate(name: string, context: Record<string, unknown>): string {
  const path = join(TEMPLATES_DIR, name);
  if (!existsSync(path)) {
    throw new Error(`Template not found: ${path}`);
  }
  const template = readFileSync(path, "utf-8");
  return Mustache.render(template, context);
}

function renderSkill(name: string, context: Record<string, unknown>): string {
  const path = join(SKILLS_DIR, name);
  if (!existsSync(path)) return "";
  const template = readFileSync(path, "utf-8");
  return Mustache.render(template, context);
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
  const projectName = opts.projectName ?? target.split("/").pop() ?? "my-project";
  const teamSize = opts.teamSize ?? preset.default_team_size;

  // Generate team
  const used = new Set<string>();
  const members: TeamMember[] = [];

  for (const role of preset.roles) {
    if (!role.required) continue;
    for (let i = 0; i < role.count && members.length < teamSize; i++) {
      const [first, last] = generateName(used);
      const fullName = `${first} ${last}`;
      used.add(fullName);
      members.push({
        name: fullName,
        agent_name: toAgentName(fullName),
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
      const fullName = `${first} ${last}`;
      used.add(fullName);
      members.push({
        name: fullName,
        agent_name: toAgentName(fullName),
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
    const safeName = m.name.toLowerCase().replace(/ /g, "_").replace(/-/g, "_");
    const rolePrefix = m.role.toLowerCase().replace(/ /g, "_");
    const cardPath = join(rosterDir, `${rolePrefix}_${safeName}.md`);
    writeFileSync(cardPath, card);
    created.push(`.claude/team/roster/${rolePrefix}_${safeName}.md`);
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
    const rendered = renderSkill(`${skill}.md.mustache`, context);
    if (rendered) {
      writeFileSync(join(skillsDir, `${skill}.md`), rendered);
      created.push(`.claude/skills/${skill}.md`);
    }
  }

  console.log(`\nCreated ${created.length} files:`);
  for (const f of created) {
    console.log(`  ${f}`);
  }
  console.log(`\nTeam framework bootstrapped for '${projectName}'!`);
}

// ---------------------------------------------------------------------------
// Subcommand interfaces & implementations
// ---------------------------------------------------------------------------

interface AddMemberOptions {
  name?: string;
  role: string;
  level: string;
  target: string;
}

export function addMember(opts: AddMemberOptions): void {
  const target = resolve(opts.target);
  const rosterDir = join(target, ".claude", "team", "roster");

  if (!existsSync(rosterDir)) {
    console.error("Error: No roster directory found. Run `2real-team init` first.");
    process.exit(1);
  }

  let name = opts.name;
  if (!name) {
    const used = new Set<string>();
    for (const f of readdirSync(rosterDir).filter((f) => f.endsWith(".md"))) {
      used.add(f.replace(/\.md$/, "").replace(/_/g, " "));
    }
    const [first, last] = generateName(used);
    name = `${first} ${last}`;
  }

  const parts = name.split(" ");
  const first = parts[0];
  const last = parts.slice(1).join(" ");
  const email = makeEmail(first, last);

  const context: Record<string, unknown> = {
    name,
    role: opts.role,
    level: opts.level,
    email,
    personality: "To be defined.",
  };

  const card = renderTemplate("roster-card.md.mustache", context);
  const safeName = name.toLowerCase().replace(/ /g, "_").replace(/-/g, "_");
  const rolePrefix = opts.role.toLowerCase().replace(/ /g, "_");
  const cardPath = join(rosterDir, `${rolePrefix}_${safeName}.md`);
  writeFileSync(cardPath, card);

  console.log(`Added: ${name} (${opts.role}, ${opts.level}) -> ${cardPath}`);
}

interface MemberOptions {
  name: string;
  target: string;
  role?: string;
  level?: string;
}

export function removeMember(opts: MemberOptions): void {
  const target = resolve(opts.target);
  const rosterDir = join(target, ".claude", "team", "roster");

  if (!existsSync(rosterDir)) {
    console.error("Error: No roster directory found.");
    process.exit(1);
  }

  const safeName = opts.name.toLowerCase().replace(/ /g, "_").replace(/-/g, "_");
  const files = readdirSync(rosterDir).filter(
    (f) => f.includes(safeName) && !f.startsWith("_departed_"),
  );

  if (files.length === 0) {
    console.error(`Error: No active roster card found for '${opts.name}'`);
    process.exit(1);
  }

  for (const f of files) {
    const oldPath = join(rosterDir, f);
    const newPath = join(rosterDir, `_departed_${f}`);
    renameSync(oldPath, newPath);
    console.log(`Archived: ${f} -> _departed_${f}`);
  }
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
  return content
    .split("\n")
    .map((line) => {
      if (line.includes(`**${field}:**`)) {
        const prefix = line.split(`**${field}:**`)[0];
        return `${prefix}**${field}:** ${value}`;
      }
      return line;
    })
    .join("\n");
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

export function updateMember(opts: MemberOptions): void {
  const target = resolve(opts.target);
  const rosterDir = join(target, ".claude", "team", "roster");

  const safeName = opts.name.toLowerCase().replace(/ /g, "_").replace(/-/g, "_");
  const files = readdirSync(rosterDir).filter(
    (f) => f.includes(safeName) && !f.startsWith("_departed_"),
  );

  if (files.length === 0) {
    console.error(`Error: No active roster card found for '${opts.name}'`);
    process.exit(1);
  }

  const cardPath = join(rosterDir, files[0]);
  let content = readFileSync(cardPath, "utf-8");

  if (opts.role) content = replaceField(content, "Role", opts.role);
  if (opts.level) content = replaceField(content, "Level", opts.level);

  writeFileSync(cardPath, content);
  console.log(`Updated: ${opts.name}`);
}

export function randomizeMember(opts: { name: string; target: string }): void {
  const target = resolve(opts.target);
  const rosterDir = join(target, ".claude", "team", "roster");

  const safeName = opts.name.toLowerCase().replace(/ /g, "_").replace(/-/g, "_");
  const files = readdirSync(rosterDir).filter(
    (f) => f.includes(safeName) && !f.startsWith("_departed_"),
  );

  if (files.length === 0) {
    console.error(`Error: No active roster card found for '${opts.name}'`);
    process.exit(1);
  }

  const oldPath = join(rosterDir, files[0]);
  const content = readFileSync(oldPath, "utf-8");

  const role = extractField(content, "Role") ?? "Software Engineer";
  const level = extractField(content, "Level") ?? "Senior";

  // Archive old
  renameSync(oldPath, join(rosterDir, `_departed_${files[0]}`));

  // Generate new identity
  const used = new Set<string>();
  for (const f of readdirSync(rosterDir).filter((f) => f.endsWith(".md"))) {
    used.add(f.replace(/\.md$/, "").replace(/_/g, " "));
  }
  const [first, last] = generateName(used);
  const newName = `${first} ${last}`;
  const email = makeEmail(first, last);

  const context: Record<string, unknown> = {
    name: newName,
    role,
    level,
    email,
    personality: randomChoice(COMMUNICATION_STYLES),
  };

  const card = renderTemplate("roster-card.md.mustache", context);
  const newSafe = newName.toLowerCase().replace(/ /g, "_").replace(/-/g, "_");
  const rolePrefix = role.toLowerCase().replace(/ /g, "_");
  const newPath = join(rosterDir, `${rolePrefix}_${newSafe}.md`);
  writeFileSync(newPath, card);

  console.log(`Archived: ${opts.name} -> _departed_${files[0]}`);
  console.log(`Created: ${newName} (${role}, ${level}) -> ${newPath}`);
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

  if (!existsSync(join(teamDir, "charter.md"))) {
    errors.push("Missing charter.md");
  }

  const rosterDir = join(teamDir, "roster");
  if (!existsSync(rosterDir)) {
    errors.push("Missing roster/ directory");
  } else {
    const active = readdirSync(rosterDir).filter(
      (f) => f.endsWith(".md") && !f.startsWith("_departed_"),
    );
    if (active.length === 0) {
      errors.push("No active roster cards found");
    } else {
      console.log(`Found ${active.length} active team members`);
    }
  }

  if (!existsSync(join(teamDir, "trust_matrix.md"))) {
    errors.push("Missing trust_matrix.md");
  }

  if (!existsSync(join(teamDir, "feedback_log.md"))) {
    errors.push("Missing feedback_log.md");
  }

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

  console.log("\nTeam Roster");
  console.log("─".repeat(60));
  console.log(
    `${"Name".padEnd(25)} ${"Role".padEnd(20)} ${"Level".padEnd(12)} Status`,
  );
  console.log("─".repeat(60));

  const files = readdirSync(rosterDir)
    .filter((f) => f.endsWith(".md"))
    .sort();

  for (const f of files) {
    const content = readFileSync(join(rosterDir, f), "utf-8");
    const name = extractField(content, "Name") ?? f.replace(".md", "");
    const role = extractField(content, "Role") ?? "?";
    const level = extractField(content, "Level") ?? "?";
    const isDeparted = f.startsWith("_departed_");
    const status = isDeparted ? "Archived" : "Active";
    console.log(
      `${name.padEnd(25)} ${role.padEnd(20)} ${level.padEnd(12)} ${status}`,
    );
  }

  const skillsDir = join(target, ".claude", "skills");
  if (existsSync(skillsDir)) {
    const skillCount = readdirSync(skillsDir).filter((f) => f.endsWith(".md")).length;
    console.log(`\nSkills installed: ${skillCount}`);
  }
}
