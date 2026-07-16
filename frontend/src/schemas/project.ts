import { z } from 'zod';

export const createProjectSchema = z.object({
  name: z.string().min(1, { error: 'Project name is required' }).max(120),
  description: z.string().max(500).default(''),
  icon: z.string().max(100).optional(),
});

export const updateProjectSchema = z.object({
  name: z.string().min(1).max(120).optional(),
  description: z.string().max(500).optional(),
  icon: z.string().max(100).optional(),
});

export type CreateProjectParams = z.infer<typeof createProjectSchema>;
export type UpdateProjectParams = z.infer<typeof updateProjectSchema>;
