import { describe, it, expect } from "vitest";
import { promptConfigSchema } from "@/schemas/workspace";
import type { FewShotExample } from "@/schemas/workspace";

describe("promptConfigSchema - fewShotExamples", () => {
  const validExample: FewShotExample = {
    userStory: "As a user, I want to log in so that I can access my account",
    tasks:
      "1. summary: Set up auth\ndescription: Create user and session tables with proper indexes.",
  };

  it("accepts valid fewShotExamples array", () => {
    const result = promptConfigSchema.safeParse({
      fewShotExamples: [validExample],
    });

    expect(result.success).toBe(true);
    if (result.success) {
      expect(result.data.fewShotExamples).toHaveLength(1);
      expect(result.data.fewShotExamples?.[0].userStory).toBe(
        validExample.userStory,
      );
    }
  });

  it("accepts empty array", () => {
    const result = promptConfigSchema.safeParse({
      fewShotExamples: [],
    });

    expect(result.success).toBe(true);
    if (result.success) {
      expect(result.data.fewShotExamples).toEqual([]);
    }
  });

  it("accepts undefined", () => {
    const result = promptConfigSchema.safeParse({});

    expect(result.success).toBe(true);
    if (result.success) {
      expect(result.data.fewShotExamples).toBeUndefined();
    }
  });

  it("accepts max 3 examples", () => {
    const result = promptConfigSchema.safeParse({
      fewShotExamples: [validExample, validExample, validExample],
    });

    expect(result.success).toBe(true);
    if (result.success) {
      expect(result.data.fewShotExamples).toHaveLength(3);
    }
  });

  it("rejects more than 3 examples", () => {
    const result = promptConfigSchema.safeParse({
      fewShotExamples: [validExample, validExample, validExample, validExample],
    });

    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues[0].message).toContain("3");
    }
  });

  it("rejects userStory shorter than 10 characters", () => {
    const result = promptConfigSchema.safeParse({
      fewShotExamples: [{ userStory: "Short", tasks: validExample.tasks }],
    });

    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues[0].message).toContain("10");
      expect(result.error.issues[0].path).toEqual([
        "fewShotExamples",
        0,
        "userStory",
      ]);
    }
  });

  it("rejects tasks shorter than 20 characters", () => {
    const result = promptConfigSchema.safeParse({
      fewShotExamples: [
        { userStory: validExample.userStory, tasks: "Too short" },
      ],
    });

    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues[0].message).toContain("20");
      expect(result.error.issues[0].path).toEqual([
        "fewShotExamples",
        0,
        "tasks",
      ]);
    }
  });

  it("rejects empty userStory", () => {
    const result = promptConfigSchema.safeParse({
      fewShotExamples: [{ userStory: "", tasks: validExample.tasks }],
    });

    expect(result.success).toBe(false);
  });

  it("rejects empty tasks", () => {
    const result = promptConfigSchema.safeParse({
      fewShotExamples: [{ userStory: validExample.userStory, tasks: "" }],
    });

    expect(result.success).toBe(false);
  });

  it("validates each example independently", () => {
    const result = promptConfigSchema.safeParse({
      fewShotExamples: [
        validExample,
        { userStory: "Invalid", tasks: validExample.tasks }, // userStory too short
      ],
    });

    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues[0].path).toEqual([
        "fewShotExamples",
        1,
        "userStory",
      ]);
    }
  });

  it("accepts null", () => {
    const result = promptConfigSchema.safeParse({
      fewShotExamples: null,
    });

    expect(result.success).toBe(true);
    if (result.success) {
      expect(result.data.fewShotExamples).toBeNull();
    }
  });

  it("allows fewShotExamples alongside other fields", () => {
    const result = promptConfigSchema.safeParse({
      systemPrompt: "You are an expert...",
      instructionTemplate: "Break this user story...",
      fewShotExamples: [validExample],
    });

    expect(result.success).toBe(true);
    if (result.success) {
      expect(result.data.systemPrompt).toBe("You are an expert...");
      expect(result.data.fewShotExamples).toHaveLength(1);
    }
  });
});
