import assert from 'node:assert/strict';
import test from 'node:test';

import {
  AI_CONTEXT_CACHE_STORAGE_KEY,
  addQuestionsToAiContext,
  readAiContextCache,
  writeAiContextCache,
} from './aiContextCache.ts';
import type { Question } from '../types';

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

test('filters malformed AI context entries and deduplicates questions', () => {
  const storage = new MemoryStorage();
  storage.setItem(AI_CONTEXT_CACHE_STORAGE_KEY, JSON.stringify([null, { title: 'missing id' }, { question_id: 'q1' }]));
  withStorage(storage, () => {
    assert.deepEqual(readAiContextCache().map((item) => item.question_id), ['q1']);
    const result = addQuestionsToAiContext([
      { question_id: 'q1', title: 'updated' } as Question,
      { question_id: 'q2', title: 'new' } as Question,
    ]);
    assert.deepEqual(result.map((item) => item.question_id), ['q1', 'q2']);
  });
});

test('AI context persistence is best-effort when storage is blocked', () => {
  const blocked = {
    getItem(): string | null { throw new Error('blocked'); },
    setItem(): void { throw new Error('blocked'); },
    removeItem(): void { throw new Error('blocked'); },
  };
  withStorage(blocked, () => {
    assert.deepEqual(readAiContextCache(), []);
    assert.doesNotThrow(() => writeAiContextCache([]));
  });
});
