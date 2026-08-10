import test from 'node:test';
import assert from 'node:assert/strict';

import { buildClassroomFollowUpTasks, listClassroomReflections, loadLatestClassroomReflection, saveClassroomReflection, setClassroomFollowUpTaskCompleted, type ClassroomReflection } from './classroomReflection.ts';

test('saves and reloads the latest classroom reflection for a project', () => {
  const store = new Map<string, string>();
  Object.defineProperty(globalThis, 'window', {
    configurable: true,
    value: {
    localStorage: {
      getItem: (key: string) => store.get(key) ?? null,
      setItem: (key: string, value: string) => { store.set(key, value); },
      removeItem: (key: string) => { store.delete(key); },
      clear: () => { store.clear(); },
      key: (index: number) => Array.from(store.keys())[index] ?? null,
      get length() { return store.size; },
    },
    },
  });

  const reflection: ClassroomReflection = {
    id: 'reflection-1',
    projectId: 'project-1',
    rating: 5,
    completed: true,
    highlights: '互动很好',
    followUp: '补充一道综合题',
    attendedPages: 6,
    createdAt: '2026-08-05T10:00:00.000Z',
    updatedAt: '2026-08-05T10:00:00.000Z',
  };

  saveClassroomReflection(reflection);
  assert.deepEqual(loadLatestClassroomReflection('project-1'), reflection);
  assert.equal(loadLatestClassroomReflection('project-2'), null);
  const tasks = buildClassroomFollowUpTasks(listClassroomReflections());
  assert.equal(tasks.length, 1);
  setClassroomFollowUpTaskCompleted(tasks[0].id, true);
  assert.deepEqual(loadLatestClassroomReflection('project-1')?.completedFollowUpTaskIds, [tasks[0].id]);
  assert.equal(buildClassroomFollowUpTasks(listClassroomReflections()).length, 0);
  assert.equal(tasks[0].title, '执行复盘行动');
});
