/**
 * Core bootstrap logic for Node CLI.
 */
interface BootstrapOptions {
    preset?: string;
    teamSize?: number;
    config?: string;
    projectName?: string;
    target: string;
    interactive: boolean;
    aiPersonas?: boolean;
    seed?: number;
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
export declare const FIRST_NAMES: string[];
export declare const LAST_NAMES: string[];
export declare const COMMUNICATION_STYLES: string[];
export declare function generateName(used: Set<string>): [string, string];
export declare function makeEmail(first: string, last: string, prefix?: string): string;
export declare function loadPreset(name: string): Preset;
export declare function listPresets(): Preset[];
interface MemberOverride {
    name?: string;
    role?: string;
    level?: string;
    personality?: string;
}
interface YamlConfig {
    preset: string;
    project_name?: string;
    team_size?: number;
    git_email_prefix?: string;
    target?: string;
    skills?: string[];
    members?: MemberOverride[];
}
export declare function loadYamlConfig(configPath: string): YamlConfig;
export declare function bootstrap(opts: BootstrapOptions): Promise<void>;
interface AddMemberOptions {
    name?: string;
    role: string;
    level: string;
    target: string;
    aiPersonas?: boolean;
    seed?: number;
}
export declare function addMember(opts: AddMemberOptions): Promise<void>;
interface MemberOptions {
    name: string;
    target: string;
    role?: string;
    level?: string;
}
export declare function removeMember(opts: MemberOptions): void;
export declare function extractField(content: string, field: string): string | null;
export declare function replaceField(content: string, field: string, value: string): string;
export declare function safeName(name: string): string;
export declare function findRosterCards(rosterDir: string, name: string): string[];
export declare function updateMember(opts: MemberOptions): void;
export declare function randomizeMember(opts: {
    name: string;
    target: string;
    aiPersonas?: boolean;
    seed?: number;
}): Promise<void>;
export declare function validateTeam(opts: {
    target: string;
}): void;
export declare function showStatus(opts: {
    target: string;
}): void;
export {};
