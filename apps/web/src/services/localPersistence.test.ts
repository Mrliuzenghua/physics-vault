import assert from 'node:assert/strict';
import test from 'node:test';

import {
  clearPersistedImportTasks,
  loadMaterialPackages,
  loadPersistedImportTasks,
  loadTemplates,
  savePersistedImportTasks,
  saveTemplate,
} from './localPersistence.ts';

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

test('filters malformed import, template, and material cache entries', () => {
  const storage = new MemoryStorage();
  storage.setItem('physics-vault.import.tasks', JSON.stringify([{ fileId: 'incomplete' }]));
  storage.setItem('physics-vault.templates', JSON.stringify([
    { id: 'bad' },
    { id: 'template-1', name: 'Template', type: 'style', config: {} },
  ]));
  storage.setItem('physics-vault.material-packages', JSON.stringify([{ id: 'incomplete' }]));
  withStorage(storage, () => {
    assert.deepEqual(loadPersistedImportTasks(), []);
    assert.deepEqual(loadTemplates().map((item) => item.id), ['template-1']);
    assert.deepEqual(loadMaterialPackages(), []);
  });
});

test('workspace persistence operations tolerate blocked storage', () => {
  const blocked = {
    getItem(): string | null { throw new Error('blocked'); },
    setItem(): void { throw new Error('blocked'); },
    removeItem(): void { throw new Error('blocked'); },
  };
  withStorage(blocked, () => {
    assert.doesNotThrow(() => savePersistedImportTasks([]));
    assert.doesNotThrow(() => clearPersistedImportTasks());
    assert.doesNotThrow(() => saveTemplate({ id: 't1', name: 'Template', type: 'style', config: {} }));
  });
});
