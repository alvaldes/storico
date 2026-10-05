import { create } from 'zustand';

/**
 * Full-page blocking loader timing constants.
 *
 * Both values are load-bearing:
 * - DELAY keeps the overlay off fast mutations (< 250 ms), which would
 *   otherwise flash a veil for every quick save.
 * - MIN_VISIBLE guarantees the overlay never blinks away the instant a
 *   request settles, which reads as a flicker the eye catches.
 */
export const BLOCKING_LOADER_DELAY_MS = 250;
export const BLOCKING_LOADER_MIN_VISIBLE_MS = 400;

interface LoadingState {
  pending: number;
  visible: boolean;
}

/**
 * The overlay itself only needs (pending, visible) reactively. All the
 * timing bookkeeping lives in module-level non-reactive state below so
 * subscribers never re-render on counter churn they cannot see.
 */
export const useLoadingStore = create<LoadingState>(() => ({
  pending: 0,
  visible: false,
}));

// ── Module-level, non-reactive timing state ──

let pending = 0;
/** Timestamp of when the overlay became visible; null while hidden. */
let visibleSince: number | null = null;
let showTimer: ReturnType<typeof setTimeout> | null = null;
let hideTimer: ReturnType<typeof setTimeout> | null = null;

/** Single writer: every mutation lands here so the store can never drift. */
function sync(): void {
  useLoadingStore.setState({ pending, visible: visibleSince !== null });
}

function clearShowTimer(): void {
  if (showTimer !== null) {
    clearTimeout(showTimer);
    showTimer = null;
  }
}

function clearHideTimer(): void {
  if (hideTimer !== null) {
    clearTimeout(hideTimer);
    hideTimer = null;
  }
}

/**
 * Marks the start of one blocking request. The overlay only appears once the
 * delay elapses with `pending > 0`, so a burst of mutations shares a single
 * show timer.
 */
export function beginBlockingRequest(): void {
  pending += 1;
  // A request arriving while the overlay is being hidden must cancel that
  // hide: dropping the veil and immediately re-raising it is the flicker.
  clearHideTimer();
  if (visibleSince === null && showTimer === null) {
    showTimer = setTimeout(() => {
      showTimer = null;
      // Every begin may have been matched by an end before the delay
      // elapsed; do not raise the veil for a request that already finished.
      if (pending === 0) return;
      visibleSince = Date.now();
      sync();
    }, BLOCKING_LOADER_DELAY_MS);
  }
  sync();
}

/**
 * Marks the end of one blocking request. When the last request ends while
 * the overlay is visible, the hide is deferred until MIN_VISIBLE_MS has
 * elapsed since the veil was raised.
 */
export function endBlockingRequest(): void {
  // Unpaired end (or double end) must never drive the counter negative.
  if (pending === 0) return;
  pending -= 1;
  if (pending > 0) {
    sync();
    return;
  }
  clearShowTimer();
  // Never visible (request finished inside the delay window): nothing to hold.
  if (visibleSince === null) {
    sync();
    return;
  }
  const remaining = BLOCKING_LOADER_MIN_VISIBLE_MS - (Date.now() - visibleSince);
  hideTimer = setTimeout(() => {
    hideTimer = null;
    // A new request may have arrived inside the hide window; it already
    // cleared this timer, but re-check so a stale firing cannot hide it.
    if (pending > 0) return;
    visibleSince = null;
    sync();
  }, Math.max(0, remaining));
  sync();
}

/** Test helper: wipe every timer and counter back to the pristine state. */
export function resetBlockingLoader(): void {
  clearShowTimer();
  clearHideTimer();
  pending = 0;
  visibleSince = null;
  sync();
}
