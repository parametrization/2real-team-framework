/**
 * Mustache template rendering utilities.
 */

import { readFileSync, existsSync, readdirSync } from "node:fs";
import { resolve, join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import Mustache from "mustache";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const TEMPLATES_DIR = resolve(__dirname, "../../templates");
const SKILLS_DIR = resolve(__dirname, "../../skills");

export function renderTemplate(
  templateName: string,
  context: Record<string, unknown>,
): string {
  const path = join(TEMPLATES_DIR, templateName);
  if (!existsSync(path)) {
    throw new Error(`Template not found: ${path}`);
  }
  const template = readFileSync(path, "utf-8");
  return Mustache.render(template, context);
}

export function renderSkill(
  skillName: string,
  context: Record<string, unknown>,
): string {
  const path = join(SKILLS_DIR, skillName);
  if (!existsSync(path)) {
    throw new Error(`Skill template not found: ${path}`);
  }
  const template = readFileSync(path, "utf-8");
  return Mustache.render(template, context);
}

export function listTemplates(): string[] {
  if (!existsSync(TEMPLATES_DIR)) return [];
  return readdirSync(TEMPLATES_DIR).filter((f) => f.endsWith(".mustache")).sort();
}

export function listSkills(): string[] {
  if (!existsSync(SKILLS_DIR)) return [];
  return readdirSync(SKILLS_DIR).filter((f) => f.endsWith(".mustache")).sort();
}
