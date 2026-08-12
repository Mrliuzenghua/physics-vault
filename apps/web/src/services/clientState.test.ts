import assert from 'node:assert/strict';
import test from 'node:test';

import {
  addToBasket,
  getBasket,
  getMcpConfig,
  getSettings,
  getTheme,
  saveMcpConfig,
  saveSettings,
  saveTheme,
} from './clientState.ts';

class MemoryStorage {
  private readonly values = new Map<string, string>();

  getItem(key: string): string | null { return this.values.get(key) ?? null; }
  setItem(key: string, value: string): void { this.values.set(key, value); }
  removeItem(key: string): void { this.values.delete(key); }
}

function installStorage(storage: Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>): () => void {
  const originalWindow = globalThis.window;
  const originalStorage = globalThis.localStorage;
  Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: storage });
  Object.defineProperty(globalThis, 'window', {
    configurable: true,
    value: { localStorage: storage },
  });
  return () => {
    Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: originalStorage });
    Object.defineProperty(globalThis, 'window', { configurable: true, value: originalWindow });
  };
}

test('rejects malformed basket entries instead of crashing consumers', () => {
  const storage = new MemoryStorage();
  storage.setItem('physics_vault_basket', JSON.stringify({ question_id: 'not-an-array' }));
  const restore = installStorage(storage);
  try {
    assert.deepEqual(getBasket(), []);
    assert.deepEqual(addToBasket('question-1').map((item) => item.question_id), ['question-1']);
  } finally {
    restore();
  }
});

test('normalizes invalid settings, MCP sections, and theme values', () => {
  const storage = new MemoryStorage();
  storage.setItem('physics_vault_settings', JSON.stringify({ page_size: -10, theme: 'neon', ai_enabled: 'yes' }));
  storage.setItem('physics_vault_mcp', JSON.stringify({ vl: 'broken', llm: [], scheduling: 'broken' }));
  storage.setItem('physics_vault_theme', 'neon');
  const restore = installStorage(storage);
  try {
    assert.equal(getSettings().page_size, 20);
    assert.equal(getSettings().theme, 'system');
    assert.equal(getSettings().ai_enabled, true);
    assert.equal(getMcpConfig().vl.model_name, 'qwen3.5-ocr');
    assert.equal(getMcpConfig().scheduling.queue_size, 100);
    assert.equal(getTheme(), 'system');
  } finally {
    restore();
  }
});

test('keeps core state usable when browser storage is blocked', () => {
  const blocked = {
    getItem(): string | null { throw new Error('blocked'); },
    setItem(): void { throw new Error('blocked'); },
    removeItem(): void { throw new Error('blocked'); },
  };
  const restore = installStorage(blocked);
  try {
    assert.doesNotThrow(() => saveSettings(getSettings()));
    assert.doesNotThrow(() => saveMcpConfig(getMcpConfig()));
    assert.doesNotThrow(() => saveTheme('dark'));
    assert.equal(getTheme(), 'system');
  } finally {
    restore();
  }
});
