import type { Task } from './task';

export interface UserStory {
  id: string;
  projectId: string;
  input: string;
  status: 'pending' | 'processing' | 'completed' | 'error';
  tasks?: Task[];
}
