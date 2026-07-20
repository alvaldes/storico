import { describe, it, expect, vi, beforeEach } from 'vitest'
import * as tasksApi from '@/lib/tasks-api'
import { api, ApiRequestError } from '@/lib/api'

vi.mock('@/lib/api', () => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
  ApiRequestError: class ApiRequestErrorMock extends Error {
    status: number
    statusText: string
    detail: unknown
    constructor(status: number, statusText: string, detail: unknown) {
      super(detail ? String(detail) : `HTTP ${status}`)
      this.name = 'ApiRequestError'
      this.status = status
      this.statusText = statusText
      this.detail = detail
    }
  },
}))

const uuid = (n: number) => `${n}e8400-e29b-41d4-a716-446655440000`

describe('tasks-api', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('listTasks', () => {
    const storyId = uuid(550)

    it('fetches tasks for a given user story', async () => {
      const raw = { items: [{ id: 't1', user_story_id: storyId, title: 'DB schema', description: '', status: 'todo', priority: 'high', labels: ['db'], dependencies: [], created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z' }], total: 1, page: 1, size: 100 }
      vi.mocked(api.get).mockResolvedValue(raw)

      const result = await tasksApi.listTasks(storyId)

      expect(api.get).toHaveBeenCalledWith(`/api/v1/tasks/?user_story_id=${storyId}&page=1&size=100`)
      expect(result).toHaveLength(1)
      const t = result[0]
      expect(t.id).toBe('t1')
      expect(t.title).toBe('DB schema')
      expect(t.status).toBe('todo')
      expect(t.storyId).toBe(storyId)
    })

    it('returns empty array when no tasks exist', async () => {
      vi.mocked(api.get).mockResolvedValue({ items: [], total: 0, page: 1, size: 100 })
      const result = await tasksApi.listTasks(storyId)
      expect(result).toEqual([])
    })

    it('throws on fetch failure', async () => {
      vi.mocked(api.get).mockRejectedValue(new Error('Network error'))
      await expect(tasksApi.listTasks(storyId)).rejects.toThrow('Network error')
    })
  })

  describe('listTasksByWorkspace', () => {
    const wid = uuid(660)

    it('fetches all tasks for a workspace', async () => {
      const raw = { items: [{ id: 't1', user_story_id: uuid(550), title: 'Task', description: '', status: 'backlog', priority: 'medium', labels: [], dependencies: [], created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z' }], total: 1, page: 1, size: 200 }
      vi.mocked(api.get).mockResolvedValue(raw)

      const result = await tasksApi.listTasksByWorkspace(wid)

      expect(api.get).toHaveBeenCalledWith(`/api/v1/tasks/?workspace_id=${wid}&page=1&size=100`)
      expect(result).toHaveLength(1)
    })
  })

  describe('updateTaskStatus', () => {
    it('updates task status via PUT', async () => {
      const raw = { id: 't1', user_story_id: uuid(550), title: 'Task', description: '', status: 'in_progress', priority: 'medium', labels: [], dependencies: [], created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z' }
      vi.mocked(api.put).mockResolvedValue(raw)

      const result = await tasksApi.updateTaskStatus('t1', 'in_progress')

      expect(api.put).toHaveBeenCalledWith('/api/v1/tasks/t1', { status: 'in_progress' })
      expect(result.status).toBe('in_progress')
    })
  })

  describe('updateTask', () => {
    it('updates task fields via PUT', async () => {
      const raw = { id: 't1', user_story_id: uuid(550), title: 'Updated', description: 'New desc', status: 'backlog', priority: 'medium', labels: ['fe'], dependencies: ['dep1'], created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z' }
      vi.mocked(api.put).mockResolvedValue(raw)

      const result = await tasksApi.updateTask('t1', { title: 'Updated', description: 'New desc', labels: ['fe'], dependencies: ['dep1'] })

      expect(api.put).toHaveBeenCalledWith('/api/v1/tasks/t1', { title: 'Updated', description: 'New desc', labels: ['fe'], dependencies: ['dep1'] })
      expect(result.title).toBe('Updated')
    })

    it('can update only status', async () => {
      vi.mocked(api.put).mockResolvedValue({} as any)
      await tasksApi.updateTask('t1', { status: 'done' })
      expect(api.put).toHaveBeenCalledWith('/api/v1/tasks/t1', { status: 'done' })
    })
  })

  describe('startExtraction (async)', () => {
    const storyId = uuid(550)
    const wid = uuid(660)

    it('posts to workspace-scoped endpoint and returns pending status', async () => {
      vi.mocked(api.post).mockResolvedValue({ extraction_id: 'ext1', status: 'pending', model_used: 'llama3.2' })

      const result = await tasksApi.startExtraction(storyId, wid, { model: 'llama3.2', temperature: 0.1 })

      expect(api.post).toHaveBeenCalledWith(`/api/v1/workspaces/${wid}/extract/`, {
        user_story_id: storyId,
        model: 'llama3.2',
        temperature: 0.1,
        run_validation: false,
      })
      expect(result).toEqual({ extractionId: 'ext1', status: 'pending', modelUsed: 'llama3.2' })
    })

    it('allows calling without options', async () => {
      vi.mocked(api.post).mockResolvedValue({ extraction_id: 'ext2', status: 'pending', model_used: 'llama3.2' })

      const result = await tasksApi.startExtraction(storyId, wid)

      expect(api.post).toHaveBeenCalledWith(`/api/v1/workspaces/${wid}/extract/`, {
        user_story_id: storyId,
        model: null,
        temperature: null,
        run_validation: false,
      })
      expect(result.status).toBe('pending')
    })
  })

  describe('getExtractionStatus', () => {
    const extId = 'ext1'

    it('fetches status by extraction ID', async () => {
      vi.mocked(api.get).mockResolvedValue({
        id: extId,
        user_story_id: uuid(550),
        model_used: 'llama3.2',
        status: 'completed',
        error_info: null,
        confidence_score: 0.85,
      })

      const result = await tasksApi.getExtractionStatus(extId)

      expect(api.get).toHaveBeenCalledWith(`/api/v1/extractions/${extId}`)
      expect(result).toEqual({
        id: extId,
        userStoryId: uuid(550),
        modelUsed: 'llama3.2',
        status: 'completed',
        errorInfo: null,
        confidenceScore: 0.85,
      })
    })

    it('returns failed status with error info', async () => {
      vi.mocked(api.get).mockResolvedValue({
        id: 'ext2',
        user_story_id: uuid(550),
        model_used: 'llama3.2',
        status: 'failed',
        error_info: 'Model timeout',
        confidence_score: null,
      })

      const result = await tasksApi.getExtractionStatus('ext2')

      expect(result.status).toBe('failed')
      expect(result.errorInfo).toBe('Model timeout')
    })
  })

  /* ── Error / 401 / network state transitions (task 1.5) ── */

  describe('error propagation', () => {
    const storyId = uuid(550)
    const wid = uuid(660)

    it('propagates 401 ApiRequestError preserving status code', async () => {
      const unauthorized = new ApiRequestError(401, 'Unauthorized', 'Not authenticated')
      vi.mocked(api.post).mockRejectedValue(unauthorized)

      await expect(tasksApi.startExtraction(storyId, wid)).rejects.toThrow()
      await expect(tasksApi.startExtraction(storyId, wid)).rejects.toMatchObject({
        status: 401,
      })
    })

    it('propagates 403 ApiRequestError preserving status code', async () => {
      const forbidden = new ApiRequestError(403, 'Forbidden', 'No workspace membership')
      vi.mocked(api.post).mockRejectedValue(forbidden)

      await expect(tasksApi.startExtraction(storyId, wid)).rejects.toMatchObject({
        status: 403,
      })
    })

    it('propagates 500 ApiRequestError with server-issued detail', async () => {
      const serverError = new ApiRequestError(500, 'Internal Server Error', 'LLM provider down')
      vi.mocked(api.post).mockRejectedValue(serverError)

      const err = await tasksApi.startExtraction(storyId, wid).catch((e) => e)
      expect(err).toBeInstanceOf(ApiRequestError)
      expect((err as ApiRequestError).status).toBe(500)
      expect((err as ApiRequestError).message).toBe('LLM provider down')
    })

    it('propagates TypeError (network failure) as-is', async () => {
      // `fetch` throws TypeError on network failure / DNS miss.
      vi.mocked(api.post).mockRejectedValue(new TypeError('Failed to fetch'))

      await expect(tasksApi.startExtraction(storyId, wid)).rejects.toBeInstanceOf(TypeError)
      await expect(tasksApi.startExtraction(storyId, wid)).rejects.toThrow('Failed to fetch')
    })

    it('updateTask propagates 422 validation error with status', async () => {
      const validationError = new ApiRequestError(422, 'Unprocessable Entity', 'Invalid task id')
      vi.mocked(api.put).mockRejectedValue(validationError)

      const err = await tasksApi.updateTask('t1', { title: 'X' }).catch((e) => e)
      expect(err).toBeInstanceOf(ApiRequestError)
      expect((err as ApiRequestError).status).toBe(422)
    })

    it('updateTaskStatus rejects with ApiRequestError on 409 (task not found / conflict)', async () => {
      const conflict = new ApiRequestError(409, 'Conflict', 'Task not found')
      vi.mocked(api.put).mockRejectedValue(conflict)

      await expect(tasksApi.updateTaskStatus('t1', 'done')).rejects.toMatchObject({
        status: 409,
      })
    })

    it('listTasksByWorkspace rejects with ApiRequestError preserving status on 500', async () => {
      const serverError = new ApiRequestError(500, 'Internal Server Error', 'DB down')
      vi.mocked(api.get).mockRejectedValue(serverError)

      await expect(tasksApi.listTasksByWorkspace(wid)).rejects.toMatchObject({
        status: 500,
      })
    })

    it('getExtractionStatus rejects with TypeError on network failure', async () => {
      vi.mocked(api.get).mockRejectedValue(new TypeError('Failed to fetch'))

      await expect(tasksApi.getExtractionStatus('ext1')).rejects.toBeInstanceOf(TypeError)
    })
  })
})
