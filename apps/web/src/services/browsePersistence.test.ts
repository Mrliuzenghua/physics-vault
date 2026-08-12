import assert from 'node:assert/strict';
import test from 'node:test';

import {
  persistSearchPresets,
  readSearchPresets,
  readShareHistory,
  saveShareHistory,
} from './browsePersistence.ts';

class MemoryStorage {
  private readonly values = new Map<string, string>();

  getItem(key: string): string | null { return this.values.get(key) ?? null; }
  setItem(key: string, value: string): void { this.values.set(key, value); }
  removeItem(key: string): void { this.values.delete(key); }
}

function withStorage(
  storage: Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>,
  run: () => void,
): void {
  const originalWindow = globalThis.window;
  Object.defineProperty(globalThis, 'window', { configurable: true, value: { localStorage: storage } });
  try {
    run();
  } finally {
    Object.defineProperty(globalThis, 'window', { configurable: true, value: originalWindow });
  }
}

test('filters malformed browse history and bounds persisted entries', () => {
  const storage = new MemoryStorage();
  withStorage(storage, () => {
    storage.setItem('physics_vault.question_search_presets', JSON.stringify([
      { id: 'valid', name: 'Recent papers', filters: { year: 2026 } },
      { id: 'missing-filters', name: 'Invalid' },
    ]));
    assert.deepEqual(readSearchPresets().map((item) => item.id), ['valid']);

    persistSearchPresets(Array.from({ length: 12 }, (_, index) => ({
      id: `preset-${index}`,
      name: `Preset ${index}`,
      filters: {},
    })));
    assert.equal(readSearchPresets().length, 8);

    storage.setItem('physics_vault.question_share_history', JSON.stringify([
      { createdAt: '2026-08-13T00:00:00.000Z', questionIds: ['q-1'], text: 'Question 1' },
      { createdAt: 'invalid', questionIds: [3], text: 'Invalid' },
    ]));
    assert.deepEqual(readShareHistory().map((item) => item.questionIds), [['q-1']]);
  });
});

test('keeps browse actions usable when storage is blocked', () => {
  const blocked = {
    getItem(): string | null { throw new Error('blocked'); },
    setItem(): void { throw new Error('blocked'); },
    removeItem(): void { throw new Error('blocked'); },
  };
  withStorage(blocked, () => {
    assert.deepEqual(readSearchPresets(), []);
    assert.doesNotThrow(() => persistSearchPresets([]));
    assert.deepEqual(readShareHistory(), []);
    assert.equal(saveShareHistory({
      createdAt: '2026-08-13T00:00:00.000Z',
      questionIds: ['q-1'],
      text: 'Question 1',
    }).length, 1);
  });
});
