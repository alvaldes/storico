export interface Workspace {
  id: string;
  name: string;
  slug: string;
  icon?: string | null;
  ownerId: string;
  role: 'admin' | 'member';
  memberCount: number;
  createdAt: string;
  updatedAt: string;
}

export interface WorkspaceMember {
  userId: string;
  name: string;
  email: string;
  avatarUrl: string | null;
  role: string;
  createdAt: string;
}

/**
 * The stored LLM configuration of a workspace: the extraction configuration plus,
 * since D9, the judge's own independent block.
 *
 * The judge fields mirror `workspace_llm_configs` one-to-one (snake_case on the
 * wire): each one falls back independently to the extraction value when empty, and
 * `judgeApiKey` is stored encrypted server-side like `apiKey` — the API returns it
 * and the form masks it, the same convention the extraction credential follows.
 */
export interface WorkspaceLLMConfig {
  provider: string;
  model?: string | null;
  temperature?: number | null;
  maxTokens?: number | null;
  baseUrl?: string | null;
  apiKey?: string | null;
  judgeProvider?: string | null;
  judgeModel?: string | null;
  judgeApiKey?: string | null;
  judgeBaseUrl?: string | null;
}

export interface CustomProvider {
  id: string;
  workspaceId: string;
  name: string;
  createdAt: string;
  updatedAt: string;
}

export interface WorkspacePrompt {
  systemPrompt?: string | null;
  instructionTemplate?: string | null;
  fewShotEnabled?: boolean;
  fewShotLimit?: number;
  fewShotThreshold?: number;
}
