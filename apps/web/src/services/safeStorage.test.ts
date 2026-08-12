import assert from 'node:assert/strict';
import test from 'node:test';

import {
  isRecord,
  readJsonStorage,
  readSessionJsonStorage,
  readStorageValue,
  removeStorageValue,
  writeJsonStorage,
  writeSessionJsonStorage,
  writeStorageValue,
} from './safeStorage.ts';

class MemoryStorage {
  private readonly values = new Map<string, string>();

  getItem(key: string): string | null { return this.values.get(key) ?? null; }
  setItem(key: string, value: string): void { this.values.set(key, value); }
  removeItem(key: string): void { this.values.delete(key); }
}

function withStorage(
  storage: Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>,
  run: () => void,
  session: Pick<Storage, 'getItem' | 'setItem' | 'removeItem'> = new MemoryStorage(),
): void {
  const originalWindow = globalThis.window;
  const originalStorage = globalThis.localStorage;
  const originalSessionStorage = globalThis.sessionStorage;
  Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: storage });
  Object.defineProperty(globalThis, 'sessionStorage', { configurable: true, value: session });
  Object.defineProperty(globalThis, 'window', {
    configurable: true,
    value: { localStorage: storage, sessionStorage: session },
  });
  try {
    run();
  } finally {
    Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: originalStorage });
    Object.defineProperty(globalThis, 'sessionStorage', { configurable: true, value: originalSessionStorage });
    Object.defineProperty(globalThis, 'window', { configurable: true, value: originalWindow });
  }
}

test('reads and writes guarded JSON values', () => {
  const storage = new MemoryStorage();
  withStorage(storage, () => {
    assert.equal(writeJsonStorage('settings', { enabled: true }), true);
    assert.deepEqual(readJsonStorage('settings', {}, isRecord), { enabled: true });

    storage.setItem('settings', '[]');
    assert.deepEqual(readJsonStorage('settings', { fallback: true }, isRecord), { fallback: true });
    storage.setItem('settings', '{broken');
    assert.deepEqual(readJsonStorage('settings', { fallback: true }), { fallback: true });
    assert.equal(removeStorageValue('settings'), true);
    assert.equal(readStorageValue('settings'), null);
  });
});

test('returns fallbacks and false writes when storage is unavailable', () => {
  const blocked = {
    getItem(): string | null { throw new Error('blocked'); },
    setItem(): void { throw new Error('blocked'); },
    removeItem(): void { throw new Error('blocked'); },
  };
  withStorage(blocked, () => {
    assert.equal(readStorageValue('key'), null);
    assert.deepEqual(readJsonStorage('key', []), []);
    assert.equal(writeStorageValue('key', 'value'), false);
    assert.equal(writeJsonStorage('key', { value: true }), false);
    assert.equal(removeStorageValue('key'), false);
    assert.deepEqual(readSessionJsonStorage('key', {}), {});
    assert.equal(writeSessionJsonStorage('key', { value: true }), false);
  }, blocked);
});

test('keeps session JSON separate from persistent storage', () => {
  const storage = new MemoryStorage();
  const session = new MemoryStorage();
  withStorage(storage, () => {
    assert.equal(writeSessionJsonStorage('secret', { token: 'session-only' }), true);
    assert.deepEqual(readSessionJsonStorage('secret', {}, isRecord), { token: 'session-only' });
    assert.equal(storage.getItem('secret'), null);
  }, session);
});
