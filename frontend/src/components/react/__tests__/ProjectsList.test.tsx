import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ProjectsList } from '@/components/react/ProjectsList';
import { useProjectStore } from '@/stores/projectStore';
import type { Project } from '@/types/project';

function makeProject(id: string, name: string): Project {
  return {
    id,
    name,
    description: '',
    workspaceId: 'ws-a',
    createdBy: 'user-1',
    createdAt: '2026-01-01T00:00:00Z',
    updatedAt: '2026-01-01T00:00:00Z',
    storyCount: 0,
  };
}

describe('ProjectsList — View in Kanban link (view-in-kanban, WU2)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useProjectStore.setState({
      projects: [makeProject('project-a', 'Project A'), makeProject('project-b', 'Project B')],
      loading: false,
      saving: false,
      error: null,
      fetchProjects: vi.fn().mockResolvedValue(undefined),
    });
  });

  it('reveals one "Kanban" link per card menu, each carrying that card\'s project id', async () => {
    const user = userEvent.setup();
    render(<ProjectsList locale="en" />);

    await screen.findByText('Project A');

    // The two cards' dropdown triggers are icon-only buttons with no
    // accessible name, so they are indistinguishable by role+name. Select
    // them the honest way: every button with aria-haspopup="menu", in DOM
    // order, which mirrors the order of the cards.
    const triggers = screen
      .getAllByRole('button')
      .filter((button) => button.getAttribute('aria-haspopup') === 'menu');
    expect(triggers).toHaveLength(2);

    for (const [index, projectId] of ['project-a', 'project-b'].entries()) {
      await user.click(triggers[index]);

      // DropdownMenuContent renders through MenuPrimitive.Portal, so the
      // menu's items live outside the card subtree; query from `screen`.
      // Base UI forces role="menuitem" onto every item — even one rendered
      // as an <a> via the render prop — so query by menuitem; the anchor
      // semantics are asserted by the href below.
      const link = await screen.findByRole('menuitem', { name: 'Kanban' });
      expect(link).toHaveAttribute('href', `/en/kanban?project=${projectId}`);

      // Close this menu before opening the next: while a Base UI menu is
      // open the rest of the page is inert, so the next trigger's click
      // would only close this menu instead of opening the other one.
      await user.keyboard('{Escape}');
    }
  });

  it('stops the menu trigger\'s click from racing the card\'s own navigation to the project detail', async () => {
    const user = userEvent.setup();
    render(<ProjectsList locale="en" />);
    await screen.findByText('Project A');

    // The containment test targets the menu trigger, not the "View in
    // Kanban" link: the link is a DropdownMenuItem whose content renders
    // through MenuPrimitive.Portal, so its click never passes through the
    // card at all. The trigger, still inside the card's clickable wrapper,
    // is the one control whose containment matters.
    //
    // jsdom 29 keeps `window.location` unforgeable, so `window.location.assign`
    // itself cannot be spied. The card's handler runs while the click bubbles
    // through React's container, so a click that escapes the trigger is
    // witnessed by a bubbling listener on `document`: if it fires there, the
    // card's `window.location.assign('/en/projects/<id>')` ran on the way
    // through. The card's `onClick={(e) => e.stopPropagation()}` wrapper must
    // keep the trigger's click from reaching it.
    const escapedClick = vi.fn();
    document.addEventListener('click', escapedClick);

    try {
      // The trigger is an icon-only button with no accessible name, so
      // select it by its menu-popup semantics, in DOM (card) order.
      const trigger = screen
        .getAllByRole('button')
        .filter((button) => button.getAttribute('aria-haspopup') === 'menu')[0];
      await user.click(trigger);

      expect(escapedClick).not.toHaveBeenCalled();
    } finally {
      document.removeEventListener('click', escapedClick);
    }
  });
});
