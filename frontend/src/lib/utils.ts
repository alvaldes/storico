import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

/** Matches standard UUID v4 format */
export const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/** Shorten a UUID to its first 8 characters (like GitHub commit hashes). */
export function shortUUID(id: string): string {
  return UUID_RE.test(id) ? id.slice(0, 8) : id;
}

/** Recursively convert object keys from snake_case to camelCase. */
export function toCamelCase<T>(obj: unknown): T {
  if (Array.isArray(obj)) {
    return obj.map(toCamelCase) as T;
  }
  if (obj !== null && typeof obj === 'object') {
    const result: Record<string, unknown> = {};
    for (const [key, value] of Object.entries(obj)) {
      const camelKey = key.replace(/_([a-z])/g, (_, c) => c.toUpperCase());
      result[camelKey] = toCamelCase(value);
    }
    return result as T;
  }
  return obj as T;
}

/** Recursively convert object keys from camelCase to snake_case. */
export function toSnakeCase<T>(obj: unknown): T {
  if (Array.isArray(obj)) {
    return obj.map(toSnakeCase) as T;
  }
  if (obj !== null && typeof obj === 'object') {
    const result: Record<string, unknown> = {};
    for (const [key, value] of Object.entries(obj)) {
      const snakeKey = key.replace(/[A-Z]/g, (c) => `_${c.toLowerCase()}`);
      result[snakeKey] = toSnakeCase(value);
    }
    return result as T;
  }
  return obj as T;
}
