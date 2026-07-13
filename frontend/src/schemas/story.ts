import { z } from 'zod';

export const createStorySchema = z.object({
    projectId: z.string().uuid(),
  actor: z.string().min(1, { error: 'Actor is required' }).max(100),
  feature: z.string().min(1, { error: 'Feature is required' }).max(300),
  benefit: z.string().min(1, { error: 'Benefit is required' }).max(300),
  rawText: z.string().max(2000).default(''),
});

export const updateStorySchema = z.object({
  actor: z.string().min(1).max(100).optional(),
  feature: z.string().min(1).max(300).optional(),
  benefit: z.string().min(1).max(300).optional(),
  rawText: z.string().max(2000).optional(),
});

export type CreateStoryParams = z.infer<typeof createStorySchema>;
export type UpdateStoryParams = z.infer<typeof updateStorySchema>;
