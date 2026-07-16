export interface Project {
  id: string;
  name: string;
  description: string;
  icon?: string | null;
  workspaceId: string;
  createdBy: string | null;
  createdAt: string;
  updatedAt: string;
  storyCount: number;
}
