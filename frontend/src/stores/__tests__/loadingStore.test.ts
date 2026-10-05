import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  BLOCKING_LOADER_DELAY_MS,
  BLOCKING_LOADER_MIN_VISIBLE_MS,
  beginBlockingRequest,
  endBlockingRequest,
  resetBlockingLoader,
  useLoadingStore,
} from '@/stores/loadingStore';

/**
 * The store reads wall-clock time (Date.now()) to enforce the minimum
 * visible window, so the fake timer clock is pinned with setSystemTime and
 * both clocks are advanced together.
 */
describe('loadingStore — blocking loader timing', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(0);
    resetBlockingLoader();
  });

  afterEach(() => {
    resetBlockingLoader();
    vi.useRealTimers();
  });

  it('never becomes visible for a request that ends inside the delay window', () => {
    beginBlockingRequest();
    expect(useLoadingStore.getState().visible).toBe(false);

    vi.advanceTimersByTime(BLOCKING_LOADER_DELAY_MS - 1);
    endBlockingRequest();

    // Advancing past the delay must not raise the veil for a finished request.
    vi.advanceTimersByTime(BLOCKING_LOADER_DELAY_MS * 2);
    expect(useLoadingStore.getState().visible).toBe(false);
  });

  it('becomes visible exactly after the delay for a slow request, and not before', () => {
    beginBlockingRequest();
    vi.advanceTimersByTime(BLOCKING_LOADER_DELAY_MS - 1);
    expect(useLoadingStore.getState().visible).toBe(false);

    vi.advanceTimersByTime(1);
    expect(useLoadingStore.getState().visible).toBe(true);
  });

  it('holds the veil for the full MIN_VISIBLE_MS when the request ends inside that window', () => {
    vi.setSystemTime(10_000);
    beginBlockingRequest();
    vi.advanceTimersByTime(BLOCKING_LOADER_DELAY_MS);
    expect(useLoadingStore.getState().visible).toBe(true);

    endBlockingRequest();
    // The veil must not drop the instant the request settles.
    expect(useLoadingStore.getState().visible).toBe(true);

    vi.advanceTimersByTime(BLOCKING_LOADER_MIN_VISIBLE_MS - 1);
    expect(useLoadingStore.getState().visible).toBe(true);

    vi.advanceTimersByTime(1);
    expect(useLoadingStore.getState().visible).toBe(false);
  });

  it('hides as soon as the last request ends when it already outlived the minimum window', () => {
    // The minimum is measured from the moment the veil appeared, not from the
    // moment the work finished: the anti-flicker floor exists to stop a SHORT
    // request from blinking, never to hold the veil open 400 ms past a request
    // the user has already watched run for ten seconds. This covers the branch
    // where `remaining` is negative, which no other test in this file reaches.
    //
    // It pins the OUTCOME — hidden after one flush of the timer queue — and not
    // the `Math.max(0, remaining)` clamp itself. `setTimeout` already normalizes
    // a negative delay to 0, so deleting the clamp leaves this test green; the
    // clamp is intent, not behaviour, and nothing here claims otherwise.
    vi.setSystemTime(0);
    beginBlockingRequest();
    vi.advanceTimersByTime(BLOCKING_LOADER_DELAY_MS);
    expect(useLoadingStore.getState().visible).toBe(true);

    vi.advanceTimersByTime(10_000);
    endBlockingRequest();

    // Not a single extra millisecond: the clamp schedules the hide at 0 ms, so
    // one flush of the timer queue is all it takes. (It is still a scheduled
    // macrotask rather than a synchronous write — that is why this is not a
    // bare assertion on the line above.)
    vi.advanceTimersByTime(0);
    expect(useLoadingStore.getState().visible).toBe(false);
  });

  it('keeps the overlay up across overlapping requests until the last one ends', () => {
    beginBlockingRequest();
    vi.advanceTimersByTime(BLOCKING_LOADER_DELAY_MS);
    expect(useLoadingStore.getState().visible).toBe(true);

    beginBlockingRequest();
    endBlockingRequest();
    // The first request ended, but the second is still in flight.
    vi.advanceTimersByTime(BLOCKING_LOADER_MIN_VISIBLE_MS * 2);
    expect(useLoadingStore.getState().visible).toBe(true);

    endBlockingRequest();
    vi.advanceTimersByTime(BLOCKING_LOADER_MIN_VISIBLE_MS);
    expect(useLoadingStore.getState().visible).toBe(false);
    expect(useLoadingStore.getState().pending).toBe(0);
  });

  it('never drops visible between a request ending and a new one starting in the hide window', () => {
    beginBlockingRequest();
    vi.advanceTimersByTime(BLOCKING_LOADER_DELAY_MS);

    endBlockingRequest();
    // The hide timer is now scheduled; a new request arrives inside the window.
    vi.advanceTimersByTime(BLOCKING_LOADER_MIN_VISIBLE_MS - 100);
    expect(useLoadingStore.getState().visible).toBe(true);

    beginBlockingRequest();
    // Advance well past both the old hide deadline and the new minimum window:
    // visibility must have been continuous, never observed false in between.
    vi.advanceTimersByTime(BLOCKING_LOADER_MIN_VISIBLE_MS * 3);
    expect(useLoadingStore.getState().visible).toBe(true);

    endBlockingRequest();
    vi.advanceTimersByTime(BLOCKING_LOADER_MIN_VISIBLE_MS);
    expect(useLoadingStore.getState().visible).toBe(false);
  });

  it('never drives pending negative on an unpaired end', () => {
    endBlockingRequest();
    expect(useLoadingStore.getState().pending).toBe(0);
    expect(useLoadingStore.getState().visible).toBe(false);

    beginBlockingRequest();
    endBlockingRequest();
    endBlockingRequest();
    endBlockingRequest();
    expect(useLoadingStore.getState().pending).toBe(0);
  });

  it('resetBlockingLoader returns the store to the pristine state even mid-flight', () => {
    beginBlockingRequest();
    vi.advanceTimersByTime(BLOCKING_LOADER_DELAY_MS);
    expect(useLoadingStore.getState().visible).toBe(true);

    resetBlockingLoader();
    expect(useLoadingStore.getState()).toEqual({ pending: 0, visible: false });
  });
});
