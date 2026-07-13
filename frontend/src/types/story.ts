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
