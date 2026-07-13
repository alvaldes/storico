export interface Task {
  id: string;
  storyId: string;
  title: string;
  description: string;
  labels: string[];
  dependencies: string[];
  status: string;
  priority: string;
  createdAt: string;
  updatedAt: string;
}
