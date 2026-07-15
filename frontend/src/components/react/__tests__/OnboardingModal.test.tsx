import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { OnboardingModal } from '@/components/react/OnboardingModal';
import { useAuthStore } from '@/stores/authStore';

// Mock the completeOnboarding API call
vi.mock('@/lib/user-api', () => ({
  completeOnboarding: vi.fn().mockResolvedValue(undefined),
}));

describe('OnboardingModal', () => {
  beforeEach(() => {
    // Reset auth store
    useAuthStore.setState({
      user: { id: '1', email: 'test@test.com', name: 'Test' },
      loading: false,
      isFirstLogin: true,
      workspaceName: 'Auto Workspace',
    });
  });

  it('renders the modal with step 1 visible by default', async () => {
    render(<OnboardingModal locale="en" />);

    // The modal dialog should be visible
    await waitFor(() => {
      expect(screen.getByText('Welcome to Storico')).toBeInTheDocument();
    });

    // Step 1 content should be visible
    expect(screen.getByText('Name your workspace')).toBeInTheDocument();

    // Progress indicator should show step 1 of 3
    expect(screen.getByText('Step 1 of 3')).toBeInTheDocument();

    // Skip and Next buttons should be present
    expect(screen.getByText('Skip')).toBeInTheDocument();
    expect(screen.getByText('Next')).toBeInTheDocument();
  });

  it('navigates through all 3 steps when clicking Next', async () => {
    const user = userEvent.setup();
    render(<OnboardingModal locale="en" />);

    // Wait for modal to render
    await waitFor(() => {
      expect(screen.getByText('Welcome to Storico')).toBeInTheDocument();
    });

    // Step 1: workspace name
    expect(screen.getByText('Name your workspace')).toBeInTheDocument();

    // Click Next → go to step 2
    await user.click(screen.getByText('Next'));
    await waitFor(() => {
      expect(screen.getByText('Step 2 of 3')).toBeInTheDocument();
    });
    // Tutorial cards should be visible
    expect(screen.getByText('What is Storico?')).toBeInTheDocument();
    expect(screen.getByText('How extraction works')).toBeInTheDocument();
    expect(screen.getByText('Workspaces')).toBeInTheDocument();

    // Click Next → go to step 3
    await user.click(screen.getByText('Next'));
    await waitFor(() => {
      expect(screen.getByText('Step 3 of 3')).toBeInTheDocument();
    });
    // LLM config should be visible
    expect(screen.getByText('Configure your LLM')).toBeInTheDocument();

    // "Get Started" button should appear instead of "Next"
    expect(screen.getByText('Get Started')).toBeInTheDocument();
  });

  it('calls completeOnboarding and closes modal when Skip is clicked', async () => {
    const { completeOnboarding } = await import('@/lib/user-api');
    const user = userEvent.setup();
    render(<OnboardingModal locale="en" />);

    // Wait for modal to render
    await waitFor(() => {
      expect(screen.getByText('Welcome to Storico')).toBeInTheDocument();
    });

    // Click Skip
    await user.click(screen.getByText('Skip'));

    // completeOnboarding should have been called without a workspace name
    await waitFor(() => {
      expect(completeOnboarding).toHaveBeenCalledWith();
    });

    // isFirstLogin should be false after skipping
    expect(useAuthStore.getState().isFirstLogin).toBe(false);
  });

  it('shows close button (X) and calls handleSkip on click', async () => {
    const { completeOnboarding } = await import('@/lib/user-api');
    const user = userEvent.setup();
    render(<OnboardingModal locale="en" />);

    // Wait for modal to render
    await waitFor(() => {
      expect(screen.getByText('Welcome to Storico')).toBeInTheDocument();
    });

    // Find the close button (X icon button with aria-label "Close")
    const closeButton = screen.getByRole('button', { name: 'Close' });
    expect(closeButton).toBeInTheDocument();

    // Click the close button
    await user.click(closeButton);

    // completeOnboarding should have been called
    await waitFor(() => {
      expect(completeOnboarding).toHaveBeenCalled();
    });
  });
});
