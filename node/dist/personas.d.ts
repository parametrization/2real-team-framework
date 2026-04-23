/**
 * AI persona generation via Claude API (optional feature).
 */
interface PersonaResult {
    name: string;
    personality: string;
    expertise: string;
}
interface RoleSpec {
    role: string;
    level: string;
}
interface PresetInfo {
    name: string;
    description: string;
}
declare function buildPrompt(preset: PresetInfo, roles: RoleSpec[], teamSize: number, seed?: number): string;
declare function parseResponse(text: string, expectedCount: number): PersonaResult[];
export declare function generatePersonas(preset: PresetInfo, roles: RoleSpec[], teamSize: number, seed?: number): Promise<PersonaResult[]>;
export { buildPrompt as _buildPrompt, parseResponse as _parseResponse };
export type { PersonaResult, RoleSpec, PresetInfo };
