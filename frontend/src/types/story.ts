export interface UserStory {
  id: string;
  projectId: string;
  actor: string;
  feature: string;
  benefit: string;
  rawText: string;
  status: 'pending' | 'processing' | 'completed' | 'error';
  createdAt: string;
}

export interface CreateStoryParams {
  projectId: string;
  actor: string;
  feature: string;
  benefit: string;
  rawText: string;
}

export interface UpdateStoryParams {
  actor?: string;
  feature?: string;
  benefit?: string;
  rawText?: string;
}
