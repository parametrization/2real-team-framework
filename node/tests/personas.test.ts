/**
 * Tests for AI persona generation module.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { _buildPrompt, _parseResponse, generatePersonas } from "../src/personas.js";

describe("buildPrompt", () => {
  const preset = { name: "library", description: "Open source library" };
  const roles = [{ role: "Tech Lead", level: "Staff" }];

  it("should include role info", () => {
    const prompt = _buildPrompt(preset, roles, 3);
    expect(prompt).toContain("Tech Lead");
    expect(prompt).toContain("Staff");
    expect(prompt).toContain("library");
  });

  it("should include seed when provided", () => {
    const prompt = _buildPrompt(preset, roles, 3, 42);
    expect(prompt).toContain("seed 42");
  });

  it("should request correct number of personas", () => {
    const multiRoles = [
      { role: "Manager", level: "Senior VP" },
      { role: "Engineer", level: "Senior" },
    ];
    const prompt = _buildPrompt(preset, multiRoles, 5);
    expect(prompt).toContain("Generate 2");
    expect(prompt).toContain("Return exactly 2");
  });
});

describe("parseResponse", () => {
  it("should parse valid JSON array", () => {
    const response = JSON.stringify([
      { name: "Yuki Tanaka", personality: "Analytical.", expertise: "APIs" },
      { name: "Ada Chen", personality: "Direct.", expertise: "Testing" },
    ]);
    const result = _parseResponse(response, 2);
    expect(result).toHaveLength(2);
    expect(result[0].name).toBe("Yuki Tanaka");
    expect(result[1].name).toBe("Ada Chen");
  });

  it("should handle markdown code blocks", () => {
    const response =
      "```json\n" +
      JSON.stringify([
        { name: "Test User", personality: "Friendly.", expertise: "Code" },
      ]) +
      "\n```";
    const result = _parseResponse(response, 1);
    expect(result).toHaveLength(1);
    expect(result[0].name).toBe("Test User");
  });

  it("should return empty array for invalid JSON", () => {
    expect(_parseResponse("not json", 1)).toEqual([]);
  });

  it("should return empty array for non-array JSON", () => {
    expect(_parseResponse('{"name": "test"}', 1)).toEqual([]);
  });

  it("should truncate to expected count", () => {
    const response = JSON.stringify([
      { name: "A", personality: "X.", expertise: "Y" },
      { name: "B", personality: "X.", expertise: "Y" },
      { name: "C", personality: "X.", expertise: "Y" },
    ]);
    const result = _parseResponse(response, 2);
    expect(result).toHaveLength(2);
  });

  it("should skip items with empty name", () => {
    const response = JSON.stringify([
      { name: "", personality: "X.", expertise: "Y" },
      { name: "Valid", personality: "Good.", expertise: "Z" },
    ]);
    const result = _parseResponse(response, 2);
    expect(result).toHaveLength(1);
    expect(result[0].name).toBe("Valid");
  });

  it("should skip items with empty personality", () => {
    const response = JSON.stringify([
      { name: "Test", personality: "", expertise: "Y" },
    ]);
    const result = _parseResponse(response, 1);
    expect(result).toHaveLength(0);
  });
});

describe("generatePersonas", () => {
  const preset = { name: "library", description: "Open source library" };
  const roles = [{ role: "Engineer", level: "Senior" }];
  const originalEnv = process.env.ANTHROPIC_API_KEY;

  beforeEach(() => {
    vi.spyOn(console, "warn").mockImplementation(() => {});
  });

  afterEach(() => {
    if (originalEnv !== undefined) {
      process.env.ANTHROPIC_API_KEY = originalEnv;
    } else {
      delete process.env.ANTHROPIC_API_KEY;
    }
    vi.restoreAllMocks();
  });

  it("should return empty array when ANTHROPIC_API_KEY is not set", async () => {
    delete process.env.ANTHROPIC_API_KEY;
    const result = await generatePersonas(preset, roles, 3);
    expect(result).toEqual([]);
    expect(console.warn).toHaveBeenCalledWith(
      expect.stringContaining("ANTHROPIC_API_KEY not set"),
    );
  });

  it("should return empty array when SDK is not installed", async () => {
    process.env.ANTHROPIC_API_KEY = "sk-test-key";
    // The SDK is not installed in test env, so dynamic import will fail
    const result = await generatePersonas(preset, roles, 3);
    expect(result).toEqual([]);
    expect(console.warn).toHaveBeenCalled();
  });

  it("should return empty array on API error", async () => {
    process.env.ANTHROPIC_API_KEY = "sk-test-key";
    // Mock the dynamic import to simulate an installed SDK that throws
    vi.doMock("@anthropic-ai/sdk", () => ({
      default: class MockAnthropic {
        messages = {
          create: () => {
            throw new Error("API down");
          },
        };
      },
    }));
    // Re-import to pick up the mock — but since generatePersonas uses
    // dynamic import, we need to verify the error path
    const result = await generatePersonas(preset, roles, 3);
    expect(result).toEqual([]);
    expect(console.warn).toHaveBeenCalled();
    vi.doUnmock("@anthropic-ai/sdk");
  });

  it("should return personas on successful API call", async () => {
    process.env.ANTHROPIC_API_KEY = "sk-test-key";
    const mockPersonas = [
      {
        name: "Kenji Sato",
        personality: "Direct and clear.",
        expertise: "Backend systems",
      },
    ];
    vi.doMock("@anthropic-ai/sdk", () => ({
      default: class MockAnthropic {
        messages = {
          create: async () => ({
            content: [{ text: JSON.stringify(mockPersonas) }],
          }),
        };
      },
    }));

    // Dynamic import inside generatePersonas should pick up the mock
    const { generatePersonas: freshGenerate } = await import(
      "../src/personas.js"
    );
    const result = await freshGenerate(preset, roles, 3);
    expect(result).toHaveLength(1);
    expect(result[0].name).toBe("Kenji Sato");
    expect(result[0].personality).toBe("Direct and clear.");
    vi.doUnmock("@anthropic-ai/sdk");
  });
});
