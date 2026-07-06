import { clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';

/**
 * Merges class names with Tailwind conflict resolution.
 * Combines clsx (conditional classes) with tailwind-merge (conflict resolution).
 */
export function cn(...classes: (string | undefined | null | false)[]): string {
  return twMerge(clsx(classes));
}
