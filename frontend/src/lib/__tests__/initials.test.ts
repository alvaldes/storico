import { describe, it, expect } from 'vitest';

import { getInitials } from '@/lib/initials';

describe('getInitials', () => {
  it('takes the first letter of each of the first two words, uppercased', () => {
    expect(getInitials('Ada Lovelace Byron')).toBe('AL');
  });

  it('returns one initial for a single word', () => {
    expect(getInitials('Ada')).toBe('A');
  });

  it('collapses runs of whitespace and trims the ends', () => {
    expect(getInitials('  ada   lovelace ')).toBe('AL');
  });

  it('honours an explicit max of one', () => {
    expect(getInitials('Ada Lovelace', 1)).toBe('A');
  });

  it('renders an astral-plane character whole instead of splitting its surrogate pair', () => {
    // charAt(0) on this input yields the lone surrogate '\ud83d', which renders as �.
    expect(getInitials('😀 Smith')).toBe('😀S');
  });

  it('renders a lone astral character as itself', () => {
    expect(getInitials('😀')).toBe('😀');
  });

  it('keeps a non-Latin character intact', () => {
    // `李` is BMP, so `charAt` handles it too: this pins the non-Latin path, not the fix.
    expect(getInitials('李雷')).toBe('李');
  });

  it('returns ? for an empty string', () => {
    expect(getInitials('')).toBe('?');
  });

  it('returns ? for whitespace-only input', () => {
    expect(getInitials('   ')).toBe('?');
  });
});
