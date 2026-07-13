export interface Project {
  id: string;
  name: string;
  description: string;
  ownerId: string;
  createdAt: string;
  updatedAt: string;
  storyCount: number;
}

export interface CreateProjectParams {
  name: string;
  description?: string;
}

export interface UpdateProjectParams {
  name?: string;
  description?: string;
}
