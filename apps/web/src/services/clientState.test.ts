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

function installStorage(
  storage: Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>,
  session: Pick<Storage, 'getItem' | 'setItem' | 'removeItem'> = new MemoryStorage(),
): () => void {
  const originalWindow = globalThis.window;
  const originalStorage = globalThis.localStorage;
  const originalSessionStorage = globalThis.sessionStorage;
  Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: storage });
  Object.defineProperty(globalThis, 'sessionStorage', { configurable: true, value: session });
  Object.defineProperty(globalThis, 'window', {
    configurable: true,
    value: { localStorage: storage, sessionStorage: session },
  });
  return () => {
    Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: originalStorage });
    Object.defineProperty(globalThis, 'sessionStorage', { configurable: true, value: originalSessionStorage });
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
  const restore = installStorage(blocked, blocked);
  try {
    assert.doesNotThrow(() => saveSettings(getSettings()));
    assert.doesNotThrow(() => saveMcpConfig(getMcpConfig()));
    assert.doesNotThrow(() => saveTheme('dark'));
    assert.equal(getTheme(), 'system');
  } finally {
    restore();
  }
});

test('stores MCP keys in the current session without persisting them', () => {
  const storage = new MemoryStorage();
  const session = new MemoryStorage();
  const restore = installStorage(storage, session);
  try {
    const config = getMcpConfig();
    config.vl.api_key = 'vl-secret';
    config.llm.api_key = 'llm-secret';
    saveMcpConfig(config);

    const persisted = JSON.parse(storage.getItem('physics_vault_mcp') || '{}');
    assert.equal(persisted.vl.api_key, '');
    assert.equal(persisted.llm.api_key, '');
    assert.equal(getMcpConfig().vl.api_key, 'vl-secret');
    assert.equal(getMcpConfig().llm.api_key, 'llm-secret');
  } finally {
    restore();
  }
});

test('migrates legacy persistent MCP keys into session storage', () => {
  const storage = new MemoryStorage();
  const session = new MemoryStorage();
  storage.setItem('physics_vault_mcp', JSON.stringify({
    vl: { api_key: 'legacy-vl' },
    llm: { api_key: 'legacy-llm' },
  }));
  const restore = installStorage(storage, session);
  try {
    const config = getMcpConfig();
    const persisted = JSON.parse(storage.getItem('physics_vault_mcp') || '{}');
    assert.equal(config.vl.api_key, 'legacy-vl');
    assert.equal(config.llm.api_key, 'legacy-llm');
    assert.equal(persisted.vl.api_key, '');
    assert.equal(persisted.llm.api_key, '');
    assert.match(session.getItem('physics_vault_mcp_session_secrets') || '', /legacy-vl/);
  } finally {
    restore();
  }
});
