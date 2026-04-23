/**
 * Preset loading and validation.
 */
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
export declare function getPreset(name: string): PresetConfig;
export declare function listPresets(): PresetConfig[];
