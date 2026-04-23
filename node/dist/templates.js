/**
 * Mustache template rendering utilities.
 */
import { readFileSync, existsSync, readdirSync } from "node:fs";
import { resolve, join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import Mustache from "mustache";
const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
function resolveDir(name) {
    const pkg = resolve(__dirname, "..", name);
    if (existsSync(pkg))
        return pkg;
    return resolve(__dirname, "../..", name);
}
const TEMPLATES_DIR = resolveDir("templates");
const SKILLS_DIR = resolveDir("skills");
export function renderTemplate(templateName, context) {
    const path = join(TEMPLATES_DIR, templateName);
    if (!existsSync(path)) {
        throw new Error(`Template not found: ${path}`);
    }
    const template = readFileSync(path, "utf-8");
    return Mustache.render(template, context);
}
export function renderSkill(skillName, context) {
    const path = join(SKILLS_DIR, skillName);
    if (!existsSync(path)) {
        throw new Error(`Skill template not found: ${path}`);
    }
    const template = readFileSync(path, "utf-8");
    return Mustache.render(template, context);
}
export function listTemplates() {
    if (!existsSync(TEMPLATES_DIR))
        return [];
    return readdirSync(TEMPLATES_DIR).filter((f) => f.endsWith(".mustache")).sort();
}
export function listSkills() {
    if (!existsSync(SKILLS_DIR))
        return [];
    return readdirSync(SKILLS_DIR).filter((f) => f.endsWith(".mustache")).sort();
}
