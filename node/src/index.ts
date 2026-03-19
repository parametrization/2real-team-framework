#!/usr/bin/env node

/**
 * 2real-team CLI — AI agent team framework for Claude Code projects.
 *
 * Node/TypeScript implementation mirroring the Python CLI.
 */

import { Command } from "commander";
import {
  bootstrap,
  addMember,
  removeMember,
  updateMember,
  randomizeMember,
  validateTeam,
  showStatus,
} from "./bootstrap.js";

const program = new Command();

program
  .name("2real-team")
  .description("AI agent team framework for Claude Code projects")
  .version("0.2.0");

program
  .command("init")
  .description("Bootstrap a new project with the team framework")
  .option("--preset <name>", "Project preset (fullstack-monorepo, data-pipeline, library)")
  .option("--team-size <n>", "Override default team size", parseInt)
  .option("--config <path>", "Path to config YAML file")
  .option("--project-name <name>", "Project name")
  .option("--target <dir>", "Target directory", ".")
  .option("--no-interactive", "Disable interactive mode")
  .option("--ai-personas", "Use Claude API to generate rich personas")
  .option("--seed <n>", "Seed for reproducible AI persona generation", parseInt)
  .action(async (opts) => {
    await bootstrap({
      preset: opts.preset,
      teamSize: opts.teamSize,
      config: opts.config,
      projectName: opts.projectName,
      target: opts.target,
      interactive: opts.interactive !== false,
      aiPersonas: opts.aiPersonas ?? false,
      seed: opts.seed,
    });
  });

program
  .command("add-member [name]")
  .description("Add a team member to the roster")
  .requiredOption("--role <role>", "Role")
  .option("--level <level>", "Level", "Senior")
  .option("--target <dir>", "Target directory", ".")
  .option("--ai-personas", "Use Claude API to generate rich persona")
  .option("--seed <n>", "Seed for reproducible AI persona generation", parseInt)
  .action(async (name, opts) => {
    await addMember({ name, role: opts.role, level: opts.level, target: opts.target, aiPersonas: opts.aiPersonas ?? false, seed: opts.seed });
  });

program
  .command("remove-member <name>")
  .description("Archive a team member")
  .option("--target <dir>", "Target directory", ".")
  .action(async (name, opts) => {
    removeMember({ name, target: opts.target });
  });

program
  .command("update-member <name>")
  .description("Update a team member's configuration")
  .option("--role <role>", "New role")
  .option("--level <level>", "New level")
  .option("--target <dir>", "Target directory", ".")
  .action(async (name, opts) => {
    updateMember({ name, role: opts.role, level: opts.level, target: opts.target });
  });

program
  .command("randomize-member <name>")
  .description("Regenerate a team member's name, background, and personality")
  .option("--target <dir>", "Target directory", ".")
  .option("--ai-personas", "Use Claude API to generate rich persona")
  .option("--seed <n>", "Seed for reproducible AI persona generation", parseInt)
  .action(async (name, opts) => {
    await randomizeMember({ name, target: opts.target, aiPersonas: opts.aiPersonas ?? false, seed: opts.seed });
  });

program
  .command("validate")
  .description("Verify charter, roster, and skills consistency")
  .option("--target <dir>", "Target directory", ".")
  .action(async (opts) => {
    validateTeam({ target: opts.target });
  });

program
  .command("status")
  .description("Show team composition and project status")
  .option("--target <dir>", "Target directory", ".")
  .action(async (opts) => {
    showStatus({ target: opts.target });
  });

program.parse();
