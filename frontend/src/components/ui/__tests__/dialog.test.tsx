import { render } from '@testing-library/react';
import { describe, it, expect } from 'vitest';

import { Dialog, DialogContent, DialogTitle } from '../dialog';
import { AlertDialog, AlertDialogContent, AlertDialogTitle } from '../alert-dialog';

/**
 * Contract tests for the dialog popup's height-ceiling and scroll primitives.
 *
 * These are class-string contracts, NOT layout tests: jsdom has no layout
 * engine, so whether an over-tall dialog is actually clipped and scrollable
 * can only be observed in a real browser (see the orchestrator's browser
 * acceptance probe). What these tests pin is that the classes the fix depends
 * on cannot be silently deleted — and, in the `overflow-hidden` case, that the
 * `cn()` call-site-wins behaviour the TaskEditor pinning relies on holds.
 */
function renderDialogProbe(contentClassName?: string) {
  return render(
    <Dialog open>
      <DialogContent className={contentClassName} showCloseButton={false}>
        <DialogTitle>Dialog probe</DialogTitle>
      </DialogContent>
    </Dialog>,
  );
}

function renderAlertDialogProbe(contentClassName?: string) {
  return render(
    <AlertDialog open>
      <AlertDialogContent className={contentClassName}>
        <AlertDialogTitle>Alert dialog probe</AlertDialogTitle>
      </AlertDialogContent>
    </AlertDialog>,
  );
}

describe('DialogContent popup classes', () => {
  it('renders a popup carrying the height-ceiling, scroll and flex-column classes', () => {
    renderDialogProbe();

    const popup = document.querySelector('[data-slot="dialog-content"]');
    expect(popup).not.toBeNull();
    // The ceiling, the scroll container and the flex column are the three
    // utilities the viewport-overflow fix rests on.
    expect(popup!.classList.contains('max-h-[calc(100dvh-2rem)]')).toBe(true);
    expect(popup!.classList.contains('overflow-y-auto')).toBe(true);
    expect(popup!.classList.contains('flex-col')).toBe(true);
  });

  it('lets a call site override the scroll with overflow-hidden (twMerge, last wins)', () => {
    // TaskEditor passes `overflow-hidden` to pin its footer and scroll only its
    // fields. That only works because `cn()` is `twMerge`-based and the call
    // site's class comes last — this assertion is what pins that dependency.
    renderDialogProbe('overflow-hidden');

    const popup = document.querySelector('[data-slot="dialog-content"]');
    expect(popup).not.toBeNull();
    expect(popup!.classList.contains('overflow-hidden')).toBe(true);
    expect(popup!.classList.contains('overflow-y-auto')).toBe(false);
  });
});

describe('AlertDialogContent popup classes', () => {
  it('renders a popup carrying the height-ceiling, scroll and flex-column classes', () => {
    renderAlertDialogProbe();

    const popup = document.querySelector('[data-slot="alert-dialog-content"]');
    expect(popup).not.toBeNull();
    expect(popup!.classList.contains('max-h-[calc(100dvh-2rem)]')).toBe(true);
    expect(popup!.classList.contains('overflow-y-auto')).toBe(true);
    expect(popup!.classList.contains('flex-col')).toBe(true);
  });
});
