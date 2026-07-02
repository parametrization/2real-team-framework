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
import { readPackageVersion } from "./version.js";

const program = new Command();

program
  .name("2real-team")
  .description("AI agent team framework for Claude Code projects")
  .version(readPackageVersion());

program
  .command("init")
  .description("Bootstrap a new project with the team framework")
  .option("--preset <name>", "Project preset (fullstack-monorepo, data-pipeline, library)")
  .option("--team-size <n>", "Override default team size", parseInt)
  .option(
    "--config <path>",
    "Path to a YAML config file — either the unified install config " +
      "(shared with framework/install/bootstrap.py) or the legacy flat team config",
  )
  .option("--project-name <name>", "Project name")
  .option("--target <dir>", "Target directory", ".")
  .option("--no-interactive", "Disable interactive mode")
  .option(
    "--non-interactive",
    "Guarantee zero prompts; the config (flags > YAML > defaults) answers everything",
  )
  .option("--ai-personas", "Use Claude API to generate rich personas")
  .option("--seed <n>", "Seed for reproducible AI persona generation", parseInt)
  .option(
    "--with-hooks",
    "Also install the framework runtime (hooks/lib/skills/config + settings wiring); default",
  )
  .option("--no-hooks", "Skip the framework runtime install (team scaffolding only)")
  .option("--owner <owner>", "SCM org/user for the framework config (scm.owner)")
  .option("--merge-model <model>", "Default merge model: wave-branch | direct-to-main")
  .option(
    "--with-ontology",
    "Seed the ontology semantic overlay + structural index (requires hooks). " +
      "Unset, follows the install config's ontology.enabled (default: on)",
  )
  .option("--no-ontology", "Skip the ontology seed + structural index")
  .action(async (opts) => {
    // Tri-state: --with-ontology => true, --no-ontology => false, neither =>
    // undefined (defer to the install config so a CLI default never silently
    // overrides a forwarded YAML).
    const withOntology =
      opts.withOntology === true ? true : opts.ontology === false ? false : undefined;
    await bootstrap({
      preset: opts.preset,
      teamSize: opts.teamSize,
      config: opts.config,
      projectName: opts.projectName,
      target: opts.target,
      interactive: opts.interactive !== false && opts.nonInteractive !== true,
      aiPersonas: opts.aiPersonas ?? false,
      seed: opts.seed,
      withHooks: opts.hooks !== false,
      owner: opts.owner,
      mergeModel: opts.mergeModel,
      withOntology,
    });
  });

program
  .command("add-member [name]")
  .description("Add a team member to the roster")
  .requiredOption("--role <role>", "Role")
  .option("--level <level>", "Level", "Senior")
  .option("--target <dir>", "Target directory", ".")
  .action(async (name, opts) => {
    addMember({ name, role: opts.role, level: opts.level, target: opts.target });
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
  .action(async (name, opts) => {
    randomizeMember({ name, target: opts.target });
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
