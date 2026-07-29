import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { useAuthStore } from '@/stores/authStore';
import { useProjectStore } from '@/stores/projectStore';
import { useStoryStore } from '@/stores/storyStore';
import { Dashboard } from '@/components/react/Dashboard';

describe('Dashboard', () => {
  beforeEach(() => {
    useAuthStore.setState({
      user: { id: '1', email: 'test@test.com', name: 'Test' },
      loading: false,
      isFirstLogin: false,
    });

    useProjectStore.setState({
      projects: [],
      loading: false,
      fetchProjects: vi.fn().mockResolvedValue(undefined),
    });

    useStoryStore.setState({
      stories: [],
      loading: false,
      fetchStories: vi.fn().mockResolvedValue(undefined),
    });
  });

  it('renders dashboard content without error', async () => {
    render(<Dashboard locale="en" />);

    await waitFor(() => {
      expect(screen.getByText('Dashboard')).toBeInTheDocument();
    });
  });
});
