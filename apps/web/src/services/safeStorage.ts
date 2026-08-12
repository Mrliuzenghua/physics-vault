export type JsonGuard<T> = (value: unknown) => value is T;

export function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

export function browserStorage(): Storage | null {
  try {
    if (typeof window !== 'undefined') return window.localStorage;
    if (typeof localStorage !== 'undefined') return localStorage;
  } catch {
    // Storage can be blocked in embedded or privacy-restricted contexts.
  }
  return null;
}

export function browserSessionStorage(): Storage | null {
  try {
    if (typeof window !== 'undefined') return window.sessionStorage;
    if (typeof sessionStorage !== 'undefined') return sessionStorage;
  } catch {
    // Session storage can be blocked independently from local storage.
  }
  return null;
}

export function readStorageValue(key: string): string | null {
  try {
    return browserStorage()?.getItem(key) ?? null;
  } catch {
    return null;
  }
}

export function writeStorageValue(key: string, value: string): boolean {
  try {
    const storage = browserStorage();
    if (!storage) return false;
    storage.setItem(key, value);
    return true;
  } catch {
    return false;
  }
}

export function removeStorageValue(key: string): boolean {
  try {
    const storage = browserStorage();
    if (!storage) return false;
    storage.removeItem(key);
    return true;
  } catch {
    return false;
  }
}

export function listStorageKeys(prefix = ''): string[] {
  try {
    const storage = browserStorage();
    if (!storage) return [];
    const keys: string[] = [];
    for (let index = 0; index < storage.length; index += 1) {
      const key = storage.key(index);
      if (key !== null && key.startsWith(prefix)) keys.push(key);
    }
    return keys;
  } catch {
    return [];
  }
}

export function readJsonStorage<T>(key: string, fallback: T, guard?: JsonGuard<T>): T {
  const raw = readStorageValue(key);
  if (!raw) return fallback;
  try {
    const parsed: unknown = JSON.parse(raw);
    return guard && !guard(parsed) ? fallback : parsed as T;
  } catch {
    return fallback;
  }
}

export function writeJsonStorage(key: string, value: unknown): boolean {
  try {
    return writeStorageValue(key, JSON.stringify(value));
  } catch {
    return false;
  }
}

export function readSessionJsonStorage<T>(key: string, fallback: T, guard?: JsonGuard<T>): T {
  try {
    const raw = browserSessionStorage()?.getItem(key);
    if (!raw) return fallback;
    const parsed: unknown = JSON.parse(raw);
    return guard && !guard(parsed) ? fallback : parsed as T;
  } catch {
    return fallback;
  }
}

export function writeSessionJsonStorage(key: string, value: unknown): boolean {
  try {
    const storage = browserSessionStorage();
    if (!storage) return false;
    storage.setItem(key, JSON.stringify(value));
    return true;
  } catch {
    return false;
  }
}
