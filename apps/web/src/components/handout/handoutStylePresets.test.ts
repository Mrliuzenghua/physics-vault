import assert from 'node:assert/strict';
import test from 'node:test';

import { DEFAULT_STYLE_CONFIG, loadPresets, savePresets } from './handoutStylePresets.ts';

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

test('ignores malformed handout presets and fills missing style defaults', () => {
  const storage = new MemoryStorage();
  storage.setItem('physics-vault.handout-style-presets', JSON.stringify([
    null,
    { id: 'incomplete', name: 'Incomplete' },
    {
      id: 'custom',
      name: 'Custom',
      config: { fontSize: 16 },
      createdAt: '2026-01-01T00:00:00Z',
      updatedAt: '2026-01-01T00:00:00Z',
    },
  ]));
  withStorage(storage, () => {
    const custom = loadPresets().find((item) => item.id === 'custom');
    assert.equal(custom?.config.fontSize, 16);
    assert.equal(custom?.config.pageSize, DEFAULT_STYLE_CONFIG.pageSize);
    assert.equal(loadPresets().some((item) => item.id === 'incomplete'), false);
  });
});

test('saving presets does not fail when storage is blocked', () => {
  const blocked = {
    getItem(): string | null { throw new Error('blocked'); },
    setItem(): void { throw new Error('blocked'); },
    removeItem(): void { throw new Error('blocked'); },
  };
  withStorage(blocked, () => {
    assert.doesNotThrow(() => savePresets([]));
  });
});
