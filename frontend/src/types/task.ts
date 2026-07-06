export interface Task {
  id: string;
  storyId: string;
  summary: string;
  description: string;
  labels: string[];
  dependencies: string[];
  status: 'backlog' | 'todo' | 'in_progress' | 'review' | 'done';
}
