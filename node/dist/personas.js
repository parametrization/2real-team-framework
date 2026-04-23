/**
 * AI persona generation via Claude API (optional feature).
 */
function buildPrompt(preset, roles, teamSize, seed) {
    const roleDescriptions = roles
        .map((r, i) => `  ${i + 1}. ${r.role} (${r.level})`)
        .join("\n");
    const seedNote = seed !== undefined
        ? `\nUse seed ${seed} for deterministic generation — always produce the same names and personalities for this seed value.`
        : "";
    return `Generate ${roles.length} team member personas for a software project team.

Project type: ${preset.name} — ${preset.description}
Team size: ${teamSize}
${seedNote}

Roles to fill:
${roleDescriptions}

For each team member, generate:
1. A culturally diverse full name (first and last)
2. A personality/communication style (1-2 sentences describing how they communicate)
3. Areas of expertise relevant to their role (1 sentence)

IMPORTANT: Names should be culturally diverse — mix of ethnicities, backgrounds, and naming conventions. Avoid common Anglo-Saxon defaults.

Return ONLY a JSON array with objects having these exact keys:
- "name": full name
- "personality": communication style description
- "expertise": areas of expertise

Example format:
[
  {"name": "Yuki Tanaka", "personality": "Analytical and precise. Favors data-driven decisions.", "expertise": "Distributed systems and API design."}
]

Return exactly ${roles.length} objects in the array. No other text.`;
}
function parseResponse(text, expectedCount) {
    let cleaned = text.trim();
    // Handle markdown code blocks
    if (cleaned.startsWith("```")) {
        const lines = cleaned.split("\n");
        const filtered = lines.filter((ln) => !ln.trim().startsWith("```"));
        cleaned = filtered.join("\n");
    }
    let result;
    try {
        result = JSON.parse(cleaned);
    }
    catch {
        return [];
    }
    if (!Array.isArray(result))
        return [];
    const personas = [];
    for (const item of result.slice(0, expectedCount)) {
        if (!item || typeof item !== "object")
            continue;
        const persona = {
            name: String(item.name ?? ""),
            personality: String(item.personality ?? ""),
            expertise: String(item.expertise ?? ""),
        };
        if (persona.name && persona.personality) {
            personas.push(persona);
        }
    }
    return personas;
}
export async function generatePersonas(preset, roles, teamSize, seed) {
    // Check for API key
    const apiKey = process.env.ANTHROPIC_API_KEY;
    if (!apiKey) {
        console.warn("Warning: ANTHROPIC_API_KEY not set. AI persona generation requires an API key.");
        return [];
    }
    // Try to load anthropic SDK
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    let AnthropicClass;
    try {
        const mod = await import("@anthropic-ai/sdk");
        AnthropicClass = mod.default;
    }
    catch {
        console.warn("Warning: @anthropic-ai/sdk not installed. Install with: npm install @anthropic-ai/sdk");
        return [];
    }
    const prompt = buildPrompt(preset, roles, teamSize, seed);
    try {
        const client = new AnthropicClass({ apiKey });
        const response = await client.messages.create({
            model: "claude-sonnet-4-20250514",
            max_tokens: 2048,
            messages: [{ role: "user", content: prompt }],
        });
        const text = response.content[0].text;
        return parseResponse(text, roles.length);
    }
    catch (err) {
        console.warn(`Warning: AI persona generation failed, using local pool: ${err}`);
        return [];
    }
}
// Export for testing
export { buildPrompt as _buildPrompt, parseResponse as _parseResponse };
