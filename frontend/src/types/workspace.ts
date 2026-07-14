export interface Workspace {
  id: string;
  name: string;
  slug: string;
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

export interface WorkspaceLLMConfig {
  provider: string;
  model?: string | null;
  temperature?: number | null;
  maxTokens?: number | null;
  baseUrl?: string | null;
}

export interface WorkspacePrompt {
  systemPrompt?: string | null;
  instructionTemplate?: string | null;
  fewShotExamples?: Record<string, unknown>[] | null;
}
