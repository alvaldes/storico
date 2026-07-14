export interface Project {
  id: string;
  name: string;
  description: string;
  workspaceId: string;
  createdBy: string | null;
  createdAt: string;
  updatedAt: string;
  storyCount: number;
}
