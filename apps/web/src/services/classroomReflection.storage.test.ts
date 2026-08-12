import assert from 'node:assert/strict';
import test from 'node:test';

import {
  listClassroomReflections,
  loadLatestClassroomReflection,
  saveClassroomReflection,
  setClassroomFollowUpTaskCompleted,
  type ClassroomReflection,
} from './classroomReflection.ts';

test('keeps classroom reflections usable when browser storage is blocked', () => {
  const originalWindow = globalThis.window;
  Object.defineProperty(globalThis, 'window', {
    configurable: true,
    value: {
      localStorage: {
        getItem(): string | null { throw new Error('blocked'); },
        setItem(): void { throw new Error('blocked'); },
        removeItem(): void { throw new Error('blocked'); },
        key(): string | null { throw new Error('blocked'); },
        get length(): number { throw new Error('blocked'); },
      },
    },
  });
  try {
    const reflection = {
      id: 'blocked-reflection',
      projectId: 'blocked-project',
      rating: 3,
      completed: false,
      highlights: '',
      followUp: '',
      attendedPages: 0,
      createdAt: '2026-08-12T00:00:00.000Z',
      updatedAt: '2026-08-12T00:00:00.000Z',
    } satisfies ClassroomReflection;

    assert.doesNotThrow(() => saveClassroomReflection(reflection));
    assert.doesNotThrow(() => setClassroomFollowUpTaskCompleted('missing-task', true));
    assert.deepEqual(listClassroomReflections(), []);
    assert.equal(loadLatestClassroomReflection(reflection.projectId), null);
  } finally {
    Object.defineProperty(globalThis, 'window', { configurable: true, value: originalWindow });
  }
});
