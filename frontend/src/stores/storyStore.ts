import { create } from 'zustand';
import type { UserStory } from '@/types/story';
import type { CreateStoryParams, UpdateStoryParams } from '@/schemas';
import * as api from '@/lib/stories-api';
import { createInflightTracker } from '@/stores/_inflight';
import { ApiRequestError } from '@/lib/api';
import { getScopedWorkspaceId } from '@/lib/workspace-scope';

// Dedupe of inflight fetchStories calls. StoriesList and Dashboard can call
// fetchStories(projectId) at the same time when mounting concurrently. Key is
// derived from projectId (or 'all') AND workspaceId (or 'all'): the workspace is
// part of the query, so two fetches for the same project in different workspaces
// are different queries and must not share a slot. Distinct keys go through
// distinct slots — that is correct, they are different queries. Slot is freed on
// settle so changing the filter and coming back still triggers a fresh fetch.
const storiesInflight = createInflightTracker<string>();

// Monotonic token of the newest fetchStories call. A response from a superseded
// call — for example the workspace the user just left — can settle after the newer
// workspace's response already landed, and applying it would put the previous
// workspace's stories back on screen. Only the newest call may write to the store.
let storiesRequestSeq = 0;

// Separate monotonic token for `fetchStory`. `fetchStories` replaces the whole
// array while `fetchStory` merges a single story into it, so the two must not share
// a token: sharing one would change how they interleave today (a single-story fetch
// resolving would cancel an unrelated list fetch and vice versa). This token only
// invalidates a single-story response whose workspace was discarded meanwhile.
let storyRequestSeq = 0;

export interface StoryErrorInfo {
  friendlyMessage: string;
  rawDetail: unknown;
  status?: number;
  errorCode?: string;
}

function extractStoryErrorInfo(err: unknown): StoryErrorInfo {
  if (err instanceof ApiRequestError) {
    return err.toErrorInfo();
  }
  if (err instanceof Error) {
    return {
      friendlyMessage: err.message,
      rawDetail: err.message,
    };
  }
  if (typeof err === 'string') {
    return {
      friendlyMessage: err,
      rawDetail: err,
    };
  }
  return {
    friendlyMessage: 'An error occurred',
    rawDetail: err,
  };
}

interface StoryState {
  stories: UserStory[];
  loading: boolean;
  saving: boolean;
  error: StoryErrorInfo | null;

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
  /**
   * Drop every workspace-scoped slice. Used when the current workspace changes:
   * stories of the previous workspace must never survive the switch.
   */
  reset: () => void;
}

export const useStoryStore = create<StoryState>((set, get) => ({
  stories: [],
  loading: false,
  saving: false,
  error: null,

  fetchStories: async (projectId?: string, workspaceId?: string) => {
    const requestId = ++storiesRequestSeq;
    set({ loading: true, stories: [], error: null });
    try {
      const inflightKey = `stories:${projectId ?? 'all'}:${workspaceId ?? 'all'}`;
      const response = await storiesInflight.run(inflightKey, () =>
        api.listStories(projectId, 1, 100, workspaceId),
      );
      if (requestId !== storiesRequestSeq) return;
      set({ stories: response.items, loading: false });
    } catch (err) {
      if (requestId !== storiesRequestSeq) return;
      const errorInfo = extractStoryErrorInfo(err);
      set({ error: errorInfo, loading: false });
    }
  },

  fetchStory: async (id) => {
    // Claimed before the request starts: this call now owns `loading`, and every
    // earlier fetchStory becomes stale for both the success and the error branch.
    const requestId = ++storyRequestSeq;
    set({ loading: true, error: null });
    try {
      const story = await api.getStory(id);
      if (requestId !== storyRequestSeq) return;
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
      if (requestId !== storyRequestSeq) return;
      const errorInfo = extractStoryErrorInfo(err);
      set({ error: errorInfo, loading: false });
    }
  },

  createStory: async (params) => {
    // A create carries no workspace id of its own, so the scope in effect when it started
    // is the only thing that can say whether its response still belongs to the workspace
    // on screen. Sampled before the request and compared after it: a switch in between
    // would otherwise add the old workspace's story to the new one's list.
    const scopeAtCall = getScopedWorkspaceId();
    set({ saving: true, error: null });
    try {
      const story = await api.createStory(params);
      if (getScopedWorkspaceId() === scopeAtCall) {
        set((state) => ({ stories: [...state.stories, story], saving: false }));
      } else {
        // Only the store write is dropped; the caller still gets the story back so the
        // form can navigate to it.
        set({ saving: false });
      }
      return story;
    } catch (err) {
      const errorInfo = extractStoryErrorInfo(err);
      set({ error: errorInfo, saving: false });
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
      const errorInfo = extractStoryErrorInfo(err);
      set({ error: errorInfo, saving: false });
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
      const errorInfo = extractStoryErrorInfo(err);
      set({ error: errorInfo, saving: false });
      throw err;
    }
  },

  getById: (id) => get().stories.find((s) => s.id === id),

  reset: () => {
    // Any inflight fetchStories or fetchStory belongs to the workspace being
    // discarded, so both tokens advance too: neither response may land on the
    // fresh, empty slice.
    storiesRequestSeq++;
    storyRequestSeq++;
    set({ stories: [], loading: false, error: null });
  },
}));
