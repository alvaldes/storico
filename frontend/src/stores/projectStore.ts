import { create } from 'zustand';
import type { Project } from '@/types/project';
import type { CreateProjectParams, UpdateProjectParams } from '@/schemas';
import * as api from '@/lib/projects-api';
import { useWorkspaceStore } from '@/stores/workspaceStore';
import { getScopedWorkspaceId, isScopeUnchanged, isScopedWorkspace } from '@/lib/workspace-scope';
import { createInflightTracker } from '@/stores/_inflight';

// Dedupe of inflight fetchProjects calls. Multiple components mounting
// simultaneously (sidebar, Dashboard, ProjectsList) all call fetchProjects()
// before the first network request resolves. The tracker makes concurrent
// callers share a single underlying promise. The slot is freed on settle,
// so explicit refresh (e.g. after createProject) still triggers a new fetch.
const projectsInflight = createInflightTracker<string>();

// Monotonic token of the newest fetchProjects call. A response from a superseded
// call — for example the workspace the user just left — can settle after the newer
// workspace's response already landed, and applying it would put the previous
// workspace's projects back in the sidebar and on the projects page. Only the
// newest call may write to the store, and only it owns the `loading` flag, so a
// superseded call that returns early can never leave the spinner stuck on.
let projectsRequestSeq = 0;

interface ProjectState {
  projects: Project[];
  loading: boolean;
  saving: boolean;
  error: string | null;

  /** Fetch all projects for the current workspace. */
  fetchProjects: () => Promise<void>;
  /** Create a new project in the current workspace. */
  createProject: (params: CreateProjectParams) => Promise<Project>;
  /** Update an existing project. */
  updateProject: (id: string, params: UpdateProjectParams) => Promise<void>;
  /** Delete a project. */
  deleteProject: (id: string) => Promise<void>;
  /** Find a project by ID in the local cache. */
  getById: (id: string) => Project | undefined;
  /**
   * Drop every workspace-scoped slice. Used when the current workspace changes:
   * projects of the previous workspace must never survive the switch.
   */
  reset: () => void;
}

export const useProjectStore = create<ProjectState>((set, get) => ({
  projects: [],
  loading: false,
  saving: false,
  error: null,

  fetchProjects: async () => {
    // Claimed before the request starts: this call now owns `loading`, and every
    // earlier call becomes stale for both the success and the error branch.
    const requestId = ++projectsRequestSeq;
    const ws = useWorkspaceStore.getState().currentWorkspace;
    if (!ws) {
      set({ projects: [], loading: false });
      return;
    }
    set({ loading: true, error: null });
    try {
      const response = await projectsInflight.run(`projects:${ws.id}`, () =>
        api.listProjects(ws.id, 1, 100),
      );
      if (requestId !== projectsRequestSeq) return;
      set({ projects: response.items, loading: false });
    } catch (err) {
      if (requestId !== projectsRequestSeq) return;
      const message = err instanceof Error ? err.message : 'Failed to fetch projects';
      set({ error: message, loading: false });
    }
  },

  createProject: async (params) => {
    const ws = useWorkspaceStore.getState().currentWorkspace;
    if (!ws) throw new Error('No workspace selected');
    // A create carries no workspace id of its own, so the scope in effect when it
    // started is the only thing that can say whether its response still belongs to the
    // workspace on screen. Sampled before the request and compared after it: a switch
    // in between would otherwise add the old workspace's project to the new one's list.
    const scopeAtCall = getScopedWorkspaceId();
    set({ saving: true, error: null });
    try {
      const project = await api.createProject(ws.id, params);
      if (isScopeUnchanged(scopeAtCall)) {
        set((state) => ({ projects: [...state.projects, project], saving: false }));
      } else {
        // Only the store write is dropped; the caller still gets the project back so
        // the form can navigate to it.
        set({ saving: false });
      }
      return project;
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to create project';
      // The banner is global, but the failure still belongs to the workspace this call started
      // in: showing it after a switch would blame the new workspace for the old one's error.
      if (isScopeUnchanged(scopeAtCall)) set({ error: message });
      // Outside the guard on purpose: `saving` says a mutation is in flight, and this one has
      // settled — the scope decides where the *result* belongs, not whether it finished.
      set({ saving: false });
      throw err;
    }
  },

  updateProject: async (id, params) => {
    const ws = useWorkspaceStore.getState().currentWorkspace;
    if (!ws) throw new Error('No workspace selected');
    set({ saving: true, error: null });
    try {
      const updated = await api.updateProject(ws.id, id, params);
      set((state) => ({
        projects: state.projects.map((p) => (p.id === id ? updated : p)),
        saving: false,
      }));
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to update project';
      // The banner is global, but it describes a request addressed to `ws.id`, so it must not
      // outlive that workspace.
      if (isScopedWorkspace(ws.id)) set({ error: message });
      // Outside the guard on purpose: `saving` says a mutation is in flight, and this one has
      // settled — the scope decides where the *result* belongs, not whether it finished.
      set({ saving: false });
      throw err;
    }
  },

  deleteProject: async (id) => {
    const ws = useWorkspaceStore.getState().currentWorkspace;
    if (!ws) throw new Error('No workspace selected');
    set({ saving: true, error: null });
    try {
      await api.deleteProject(ws.id, id);
      set((state) => ({
        projects: state.projects.filter((p) => p.id !== id),
        saving: false,
      }));
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to delete project';
      // The banner is global, but it describes a request addressed to `ws.id`, so it must not
      // outlive that workspace.
      if (isScopedWorkspace(ws.id)) set({ error: message });
      // Outside the guard on purpose: `saving` says a mutation is in flight, and this one has
      // settled — the scope decides where the *result* belongs, not whether it finished.
      set({ saving: false });
      throw err;
    }
  },

  getById: (id) => get().projects.find((p) => p.id === id),

  reset: () => {
    // Any inflight fetchProjects belongs to the workspace being discarded, so the
    // token advances too: its response must not land on the fresh, empty slice.
    projectsRequestSeq++;
    set({ projects: [], loading: false, error: null });
  },
}));
