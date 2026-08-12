import assert from 'node:assert/strict';
import test from 'node:test';

import {
  listLessonFolders,
  listSavedLessonPackages,
  loadCurrentLessonPackage,
  saveCurrentLessonPackage,
} from './lessonPackage.ts';
import type { LessonPackage } from '../types';

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

const lesson: LessonPackage = {
  id: 'lesson-1',
  title: 'Lesson',
  subtitle: '',
  source: 'compose',
  questions: [],
  knowledgeCards: [],
  textBlocks: [],
  nodes: [],
  createdAt: '2026-01-01T00:00:00Z',
  updatedAt: '2026-01-01T00:00:00Z',
};

test('keeps existing lesson storage keys and validates cached content', () => {
  const storage = new MemoryStorage();
  withStorage(storage, () => {
    saveCurrentLessonPackage(lesson);
    assert.deepEqual(loadCurrentLessonPackage(), lesson);

    storage.setItem('physics-vault.current-lesson-package', JSON.stringify({ id: 'incomplete' }));
    storage.setItem('physics-vault.lesson-package-library', JSON.stringify([lesson, { id: 'broken' }]));
    storage.setItem('physics-vault.lesson-folder-library', JSON.stringify([null, { id: 'folder-1', name: 'Folder' }]));
    assert.equal(loadCurrentLessonPackage(), null);
    assert.deepEqual(listSavedLessonPackages().map((item) => item.id), ['lesson-1']);
    assert.deepEqual(listLessonFolders().map((item) => item.id), ['folder-1']);
  });
});

test('lesson package writes remain best-effort when storage is blocked', () => {
  const blocked = {
    getItem(): string | null { throw new Error('blocked'); },
    setItem(): void { throw new Error('blocked'); },
    removeItem(): void { throw new Error('blocked'); },
  };
  withStorage(blocked, () => {
    assert.equal(loadCurrentLessonPackage(), null);
    assert.doesNotThrow(() => saveCurrentLessonPackage(lesson));
  });
});
