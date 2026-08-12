import assert from 'node:assert/strict';
import test from 'node:test';

import {
  isRecord,
  readJsonStorage,
  readStorageValue,
  writeJsonStorage,
  writeStorageValue,
} from './safeStorage.ts';

class MemoryStorage {
  private readonly values = new Map<string, string>();

  getItem(key: string): string | null { return this.values.get(key) ?? null; }
  setItem(key: string, value: string): void { this.values.set(key, value); }
  removeItem(key: string): void { this.values.delete(key); }
}

function withStorage(storage: Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>, run: () => void): void {
  const originalWindow = globalThis.window;
  const originalStorage = globalThis.localStorage;
  Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: storage });
  Object.defineProperty(globalThis, 'window', { configurable: true, value: { localStorage: storage } });
  try {
    run();
  } finally {
    Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: originalStorage });
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
  });
});
