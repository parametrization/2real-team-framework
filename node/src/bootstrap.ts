/**
 * Core bootstrap logic for Node CLI.
 */

import { readFileSync, mkdirSync, writeFileSync, existsSync } from "node:fs";
import { resolve, join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import Mustache from "mustache";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const TEMPLATES_DIR = resolve(__dirname, "../../templates");
const PRESETS_DIR = resolve(__dirname, "../../presets");
const SKILLS_DIR = resolve(__dirname, "../../skills");

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
  role: string;
  level: string;
  email: string;
  reports_to: string;
  personality: string;
}

const FIRST_NAMES = [
  "Aisha", "Amara", "Andrei", "Carolina", "Chen", "Dmitri",
  "Elena", "Fatima", "Hiro", "Ibrahim", "Jada", "Kai", "Kwame",
  "Lena", "Mei-Lin", "Nadia", "Omar", "Priya", "Ravi", "Renaud",
  "Sakura", "Sunita", "Tariq", "Tomasz", "Yara", "Zara",
];

const LAST_NAMES = [
  "Asante", "Al-Rashidi", "Bianchi", "Chang", "Diallo", "Eriksson",
  "García", "Hadid", "Inoue", "Jensen", "Krishnamurthy",
  "López", "Nakamura", "Okonkwo", "Petrova", "Qureshi",
  "Rossi", "Singh", "Tanaka", "Volkov", "Wójcik", "Zhang",
];

const STYLES = [
  "Direct and structured. Prefers bullet points and numbered lists over prose.",
  "Deliberate and thorough. Reads the entire thread before responding.",
  "Enthusiastic and collaborative. Brings energy to discussions.",
  "Analytical and precise. Favors data-driven decisions.",
  "Pragmatic and concise. Focuses on what needs to get done.",
];

function randomChoice<T>(arr: T[]): T {
  return arr[Math.floor(Math.random() * arr.length)];
}

function generateName(used: Set<string>): [string, string] {
  for (let i = 0; i < 100; i++) {
    const first = randomChoice(FIRST_NAMES);
    const last = randomChoice(LAST_NAMES);
    const full = `${first} ${last}`;
    if (!used.has(full)) return [first, last];
  }
  throw new Error("Could not generate unique name");
}

function makeEmail(first: string, last: string): string {
  const clean = (s: string) => s.normalize("NFD").replace(/[\u0300-\u036f]/g, "");
  return `${clean(first)}.${clean(last)}@gmail.com`;
}

function loadPreset(name: string): Preset {
  const path = join(PRESETS_DIR, `${name}.json`);
  if (!existsSync(path)) {
    throw new Error(`Unknown preset: ${name}`);
  }
  return JSON.parse(readFileSync(path, "utf-8"));
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
      used.add(`${first} ${last}`);
      members.push({
        name: `${first} ${last}`,
        role: role.role,
        level: role.level,
        email: makeEmail(first, last),
        reports_to: "",
        personality: randomChoice(STYLES),
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
        personality: randomChoice(STYLES),
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
    const card = renderTemplate("roster-card.md.mustache", m);
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
