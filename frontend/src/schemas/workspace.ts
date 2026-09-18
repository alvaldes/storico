import { z } from 'zod';

import {
  READINESS_FIELD_TO_FORM_KEY,
  missingLLMConfigFields,
} from '@/lib/llm-config-readiness';
import {
  PROVIDER_NAME_MAX_LENGTH,
  isValidProviderName,
  normalizeProviderName,
} from '@/lib/llm-providers';

export const createWorkspaceSchema = z.object({
  name: z.string().min(1, { message: 'Workspace name is required' }).max(255),
  slug: z.string().max(100).optional(),
  icon: z.string().max(100).optional(),
});

export const updateWorkspaceSchema = z.object({
  name: z.string().min(1).max(255).optional(),
  slug: z.string().max(100).optional(),
  icon: z.string().max(100).optional(),
});

export const addMemberSchema = z.object({
  userId: z.string().uuid({ message: 'Invalid user ID format' }),
});

export const transferOwnershipSchema = z.object({
  newOwnerId: z.string().uuid({ message: 'Invalid user ID format' }),
});

/**
 * The bounds the temperature and max-token controls and the schema agree on.
 *
 * Exported so the slider and the number input read the same numbers the schema
 * enforces: a control that offers a value the schema refuses is a validation error
 * the user cannot avoid. The API declares no range for either field — only these
 * controls do — so these are the only copy, not a mirror.
 */
export const LLM_TEMPERATURE_RANGE = { min: 0, max: 2, step: 0.1 } as const;
export const LLM_MAX_TOKENS_RANGE = { min: 256, max: 8192, step: 256 } as const;

/**
 * The lengths the API stores, mirrored from `LLMConfigRequest` in
 * `backend/src/storico/api/schemas/workspace_llm_config.py`.
 *
 * The backend is authoritative and the frontend cannot import it, so the mirror guard
 * (`lib/__tests__/llm-config-readiness-mirror.test.ts`) reads that file and fails on
 * any drift. `provider` reuses the provider vocabulary's own constant: both are the
 * same 50-wide column, and the constant already backs the length rule.
 */
export const LLM_MODEL_MAX_LENGTH = 100;
export const LLM_ENDPOINT_MAX_LENGTH = 500;
export const LLM_API_KEY_MAX_LENGTH = 500;

/**
 * The stable code a draft validation issue carries.
 *
 * Zod's default prose is not UI copy: it would arrive in English inside a Spanish
 * page. The form translates these codes instead, and shows an unknown one as-is so a
 * new rule is visible rather than silently dropped.
 */
export const LLM_CONFIG_ISSUE_CODES = [
  'required',
  'too_long',
  'invalid_url',
  'out_of_range',
] as const;
export type LLMConfigIssueCode = (typeof LLM_CONFIG_ISSUE_CODES)[number];

/** An absolute http(s) endpoint, or the empty string that means "use the default". */
function isEndpointOrEmpty(value: string): boolean {
  if (value.trim() === '') return true;
  try {
    const url = new URL(value);
    return url.protocol === 'http:' || url.protocol === 'https:';
  } catch {
    return false;
  }
}

/**
 * The payload `PUT /settings/llm` accepts.
 *
 * Every field is optional because the route merges what it receives onto the stored
 * row, and because onboarding legitimately saves a bare `{ provider }` — the rest of
 * the configuration is filled in later from Workspace Settings. Complete drafts are
 * validated by {@link llmConfigDraftSchema}; this one is the wire contract.
 */
export const llmConfigSchema = z.object({
  provider: z.string().max(PROVIDER_NAME_MAX_LENGTH).optional(),
  model: z.string().max(LLM_MODEL_MAX_LENGTH).optional(),
  temperature: z.number().min(LLM_TEMPERATURE_RANGE.min).max(LLM_TEMPERATURE_RANGE.max).optional(),
  maxTokens: z
    .number()
    .int()
    .min(LLM_MAX_TOKENS_RANGE.min)
    .max(LLM_MAX_TOKENS_RANGE.max)
    .optional(),
  baseUrl: z.string().max(LLM_ENDPOINT_MAX_LENGTH).optional(),
  apiKey: z.string().max(LLM_API_KEY_MAX_LENGTH).optional(),
});

/**
 * The draft the settings form holds, validated before it is saved.
 *
 * A save is refused while this fails, so an incomplete configuration is never
 * persisted into a workspace that then cannot extract. Two kinds of rule meet here:
 * each field's own bound, and the completeness rule every provider family has to
 * satisfy ({@link missingLLMConfigFields}), which raises one issue per missing field
 * on that field's own path.
 *
 * The numbers are present-and-in-range rather than optional: the form always holds a
 * value for them, and a stored value that predates these bounds becomes a visible,
 * fixable error instead of a silent one.
 */
export const llmConfigDraftSchema = z
  .object({
    provider: z
      .string()
      .min(1, { message: 'required' })
      .max(PROVIDER_NAME_MAX_LENGTH, { message: 'too_long' }),
    model: z.string().max(LLM_MODEL_MAX_LENGTH, { message: 'too_long' }),
    temperature: z
      .number()
      .min(LLM_TEMPERATURE_RANGE.min, { message: 'out_of_range' })
      .max(LLM_TEMPERATURE_RANGE.max, { message: 'out_of_range' }),
    maxTokens: z
      .number({ message: 'out_of_range' })
      .int({ message: 'out_of_range' })
      .min(LLM_MAX_TOKENS_RANGE.min, { message: 'out_of_range' })
      .max(LLM_MAX_TOKENS_RANGE.max, { message: 'out_of_range' }),
    baseUrl: z
      .string()
      .max(LLM_ENDPOINT_MAX_LENGTH, { message: 'too_long' })
      .refine(isEndpointOrEmpty, { message: 'invalid_url' }),
    apiKey: z.string().max(LLM_API_KEY_MAX_LENGTH, { message: 'too_long' }),
  })
  .superRefine((values, ctx) => {
    // One issue per missing field, on that field's own path, so the form can put the
    // red message under the input it belongs to instead of only listing the gaps.
    for (const field of missingLLMConfigFields(values)) {
      ctx.addIssue({
        code: 'custom',
        message: 'required',
        path: [READINESS_FIELD_TO_FORM_KEY[field]],
      });
    }
  });

export const promptConfigSchema = z.object({
  systemPrompt: z.string().optional(),
  instructionTemplate: z.string().optional(),
  fewShotEnabled: z.boolean().optional(),
  fewShotLimit: z.number().int().min(1).max(10).optional(),
  fewShotThreshold: z.number().min(0).max(1).optional(),
});

/**
 * A custom provider name, validated before the round trip.
 *
 * The name is normalized the way the backend normalizes it (trimmed, casing kept),
 * then measured against the same rule — length and the two reserved names — so a
 * rejected name never costs a request. The backend remains authoritative; this only
 * spares the user the wait.
 */
export const customProviderNameSchema = z.object({
  name: z
    .string()
    .transform((value) => normalizeProviderName(value))
    .refine((value) => isValidProviderName(value), {
      message: 'Invalid provider name',
    }),
});

export type CreateWorkspaceParams = z.infer<typeof createWorkspaceSchema>;
export type UpdateWorkspaceParams = z.infer<typeof updateWorkspaceSchema>;
export type AddMemberParams = z.infer<typeof addMemberSchema>;
export type TransferOwnershipParams = z.infer<typeof transferOwnershipSchema>;
export type LLMConfigParams = z.infer<typeof llmConfigSchema>;
export type LLMConfigDraft = z.infer<typeof llmConfigDraftSchema>;
export type PromptConfigParams = z.infer<typeof promptConfigSchema>;
export type CustomProviderNameParams = z.infer<typeof customProviderNameSchema>;
