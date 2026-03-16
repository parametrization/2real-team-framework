/**
 * Preset loading and validation.
 */

import { readFileSync, existsSync, readdirSync } from "node:fs";
import { resolve, join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const PRESETS_DIR = resolve(__dirname, "../../presets");

export interface RoleSpec {
  role: string;
  level: string;
  count: number;
  required: boolean;
}

export interface PresetConfig {
  name: string;
  description: string;
  default_team_size: number;
  roles: RoleSpec[];
  skills: string[];
  default_ci: string;
}

export function getPreset(name: string): PresetConfig {
  const path = join(PRESETS_DIR, `${name}.json`);
  if (!existsSync(path)) {
    const available = listPresets().map((p) => p.name).join(", ");
    throw new Error(`Unknown preset '${name}'. Available: ${available}`);
  }
  return JSON.parse(readFileSync(path, "utf-8"));
}

export function listPresets(): PresetConfig[] {
  if (!existsSync(PRESETS_DIR)) return [];
  return readdirSync(PRESETS_DIR)
    .filter((f) => f.endsWith(".json"))
    .sort()
    .map((f) => JSON.parse(readFileSync(join(PRESETS_DIR, f), "utf-8")));
}
