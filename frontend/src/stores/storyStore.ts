import { create } from 'zustand';
import type { UserStory } from '@/types/story';
import type { CreateStoryParams, UpdateStoryParams } from '@/schemas';
import * as api from '@/lib/stories-api';
import { createInflightTracker } from '@/stores/_inflight';

// Dedupe of inflight fetchStories calls. StoriesList and Dashboard can call
// fetchStories(projectId) at the same time when mounting concurrently. Key is
// derived from projectId (or 'all'); distinct projectIds go through distinct
// slots — that is correct, they are different queries. Slot is freed on settle
// so changing the filter and coming back still triggers a fresh fetch.
const storiesInflight = createInflightTracker<string>();

interface StoryState {
  stories: UserStory[];
  loading: boolean;
  saving: boolean;
  error: string | null;

  /** Fetch stories, optionally filtered by project and/or workspace. */
  fetchStories: (projectId?: string, workspaceId?: string) => Promise<void>;
  /** Fetch a single story by ID. */
  fetchStory: (id: string) => Promise<void>;
  /** Create a new user story. */
  createStory: (params: CreateStoryParams) => Promise<UserStory>;
  /** Update an existing user story. */
  updateStory: (id: string, params: UpdateStoryParams) => Promise<void>;
  /** Delete a user story. */
  deleteStory: (id: string) => Promise<void>;
  /** Find a story by ID in the local cache. */
  getById: (id: string) => UserStory | undefined;
}

export const useStoryStore = create<StoryState>((set, get) => ({
  stories: [],
  loading: false,
  saving: false,
  error: null,

  fetchStories: async (projectId?: string, workspaceId?: string) => {
    set({ loading: true, stories: [], error: null });
    try {
      const inflightKey = `stories:${projectId ?? 'all'}`;
      const response = await storiesInflight.run(inflightKey, () =>
        api.listStories(projectId, 1, 100, workspaceId),
      );
      set({ stories: response.items, loading: false });
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch stories';
      set({ error: message, loading: false });
    }
  },

  fetchStory: async (id) => {
    set({ loading: true, error: null });
    try {
      const story = await api.getStory(id);
      set((state) => {
        const exists = state.stories.find((s) => s.id === id);
        return {
          stories: exists
            ? state.stories.map((s) => (s.id === id ? story : s))
            : [...state.stories, story],
          loading: false,
        };
      });
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch story';
      set({ error: message, loading: false });
    }
  },

  createStory: async (params) => {
    set({ saving: true, error: null });
    try {
      const story = await api.createStory(params);
      set((state) => ({ stories: [...state.stories, story], saving: false }));
      return story;
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to create story';
      set({ error: message, saving: false });
      throw err;
    }
  },

  updateStory: async (id, params) => {
    set({ saving: true, error: null });
    try {
      const updated = await api.updateStory(id, params);
      set((state) => ({
        stories: state.stories.map((s) => (s.id === id ? updated : s)),
        saving: false,
      }));
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to update story';
      set({ error: message, saving: false });
      throw err;
    }
  },

  deleteStory: async (id) => {
    set({ saving: true, error: null });
    try {
      await api.deleteStory(id);
      set((state) => ({
        stories: state.stories.filter((s) => s.id !== id),
        saving: false,
      }));
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to delete story';
      set({ error: message, saving: false });
      throw err;
    }
  },

  getById: (id) => get().stories.find((s) => s.id === id),
}));
