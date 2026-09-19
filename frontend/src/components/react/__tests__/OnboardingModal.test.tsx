import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { OnboardingModal } from '@/components/react/OnboardingModal';
import { useAuthStore } from '@/stores/authStore';
import { useWorkspaceStore } from '@/stores/workspaceStore';
import { KNOWN_PROVIDERS } from '@/lib/llm-providers';
import en from '@/i18n/en.json';

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
    });

    // The modal now seeds its step-1 input from workspaceStore.currentWorkspace.name
    useWorkspaceStore.setState({
      currentWorkspace: {
        id: 'ws-1',
        name: 'Auto Workspace',
        slug: 'auto-workspace',
        role: 'owner',
        createdAt: '2026-01-01T00:00:00Z',
      } as any,
      workspaces: [],
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

  it('has no close button (X) — can only dismiss via Skip or completing all steps', async () => {
    render(<OnboardingModal locale="en" />);

    await waitFor(() => {
      expect(screen.getByText('Welcome to Storico')).toBeInTheDocument();
    });

    // No button with aria-label "Close" should exist
    expect(screen.queryByRole('button', { name: 'Close' })).not.toBeInTheDocument();
  });

  it('offers exactly the known providers in the LLM select', async () => {
    const user = userEvent.setup();
    render(<OnboardingModal locale="en" />);

    await waitFor(() => {
      expect(screen.getByText('Welcome to Storico')).toBeInTheDocument();
    });
    await user.click(screen.getByText('Next'));
    await user.click(screen.getByText('Next'));
    await waitFor(() => {
      expect(screen.getByText('Step 3 of 3')).toBeInTheDocument();
    });

    // Derived from KNOWN_PROVIDERS and the catalog rather than typed out, so a provider added
    // to the list without a label here fails on the missing option instead of on a count.
    const onboarding = en.onboarding as Record<string, string>;
    const settings = en.settings as Record<string, string>;
    const expected = KNOWN_PROVIDERS.map((provider) => onboarding[`llm_${provider}`]);
    expect(expected.every((label) => typeof label === 'string' && label.length > 0)).toBe(true);

    const trigger = screen.getByLabelText('Configure your LLM');
    await user.click(trigger);
    await screen.findByRole('option', { name: expected[0] });

    // Compared as a set and without the glyphs: ordering is the component's business, and
    // `anthropicBlack` carries an SVG `<title>` that sits in the option's text content
    // without being part of the name a user reads.
    const offered = screen.getAllByRole('option').map((option) => {
      const clone = option.cloneNode(true) as HTMLElement;
      clone.querySelectorAll('svg').forEach((glyph) => glyph.remove());
      return clone.textContent?.trim();
    });
    expect(offered.sort()).toEqual([...expected].sort());

    // A label alone would also pass for an option whose value names a different provider, so
    // read one selection back: `gemini` is the only value that renders this label.
    const geminiLabel = expected[KNOWN_PROVIDERS.indexOf('gemini')];
    await user.click(await screen.findByRole('option', { name: geminiLabel }));
    await waitFor(() => expect(trigger).toHaveTextContent(settings.llm_provider_gemini));
  });
});
