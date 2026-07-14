import { z } from 'zod';

export const createWorkspaceSchema = z.object({
  name: z.string().min(1, { message: 'Workspace name is required' }).max(255),
  slug: z.string().max(100).optional(),
});

export const updateWorkspaceSchema = z.object({
  name: z.string().min(1).max(255).optional(),
  slug: z.string().max(100).optional(),
});

export const addMemberSchema = z.object({
  userId: z.string().uuid({ message: 'Invalid user ID format' }),
});

export const transferOwnershipSchema = z.object({
  newOwnerId: z.string().uuid({ message: 'Invalid user ID format' }),
});

export const llmConfigSchema = z.object({
  provider: z.string().max(50).optional(),
  model: z.string().max(100).optional(),
  temperature: z.number().min(0).max(2).optional(),
  maxTokens: z.number().int().positive().optional(),
  baseUrl: z.string().max(500).optional(),
});

export const promptConfigSchema = z.object({
  systemPrompt: z.string().optional(),
  instructionTemplate: z.string().optional(),
  fewShotExamples: z.array(z.record(z.unknown())).optional(),
});

export type CreateWorkspaceParams = z.infer<typeof createWorkspaceSchema>;
export type UpdateWorkspaceParams = z.infer<typeof updateWorkspaceSchema>;
export type AddMemberParams = z.infer<typeof addMemberSchema>;
export type TransferOwnershipParams = z.infer<typeof transferOwnershipSchema>;
export type LLMConfigParams = z.infer<typeof llmConfigSchema>;
export type PromptConfigParams = z.infer<typeof promptConfigSchema>;
