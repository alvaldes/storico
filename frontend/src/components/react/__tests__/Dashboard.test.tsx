import { describe, it, expect, vi, beforeEach } from 'vitest';
import { act, render, screen, waitFor } from '@testing-library/react';
import { useAuthStore } from '@/stores/authStore';
import { useProjectStore } from '@/stores/projectStore';
import { useStoryStore } from '@/stores/storyStore';
import { Dashboard } from '@/components/react/Dashboard';

// Mock the OnboardingModal to simplify testing — we only test its presence/absence
vi.mock('@/components/react/OnboardingModal', () => ({
  OnboardingModal: vi.fn(({ locale }: { locale?: string }) => (
    <div data-testid="onboarding-modal">Welcome to Storico (locale: {locale})</div>
  )),
}));

describe('Dashboard', () => {
  beforeEach(() => {
    // Reset auth store
    useAuthStore.setState({
      user: { id: '1', email: 'test@test.com', name: 'Test' },
      loading: false,
      isFirstLogin: false,
      workspaceName: 'Test Workspace',
    });

    // Mock store actions to avoid real API calls
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

  it('renders OnboardingModal when isFirstLogin is true', async () => {
    // Arrange — set first login to true
    useAuthStore.getState().setIsFirstLogin(true);

    // Act
    render(<Dashboard locale="en" />);

    // Wait for initial loading to finish
    await waitFor(() => {
      // When loading completes, the dashboard header appears
      expect(screen.getByText('Dashboard')).toBeInTheDocument();
    });

    // Assert — OnboardingModal should be rendered
    expect(screen.getByTestId('onboarding-modal')).toBeInTheDocument();
    expect(screen.getByText('Welcome to Storico (locale: en)')).toBeInTheDocument();
  });

  it('does NOT render OnboardingModal when isFirstLogin is false', async () => {
    // Arrange — already false from reset

    // Act
    render(<Dashboard locale="en" />);

    // Wait for initial loading to finish
    await waitFor(() => {
      expect(screen.getByText('Dashboard')).toBeInTheDocument();
    });

    // Assert — OnboardingModal should NOT be rendered
    expect(screen.queryByTestId('onboarding-modal')).not.toBeInTheDocument();
  });

  it('reacts to isFirstLogin changing from true to false', async () => {
    // Arrange — start with first login
    useAuthStore.getState().setIsFirstLogin(true);

    // Act
    render(<Dashboard locale="en" />);

    // Wait for loading to finish
    await waitFor(() => {
      expect(screen.getByText('Dashboard')).toBeInTheDocument();
    });

    // Confirm modal is visible initially
    expect(screen.getByTestId('onboarding-modal')).toBeInTheDocument();

    // Act — complete onboarding inside act() to avoid React state update warning
    act(() => {
      useAuthStore.getState().setOnboardingDone();
    });

    // Assert — modal should disappear
    await waitFor(() => {
      expect(screen.queryByTestId('onboarding-modal')).not.toBeInTheDocument();
    });
  });
});
