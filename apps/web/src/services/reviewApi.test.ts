import assert from 'node:assert/strict';
import test from 'node:test';

import { deleteReviewTask, saveReviewedQuestions } from './reviewApi.ts';

test('review client encodes task IDs for queue mutations', async () => {
  let url = '';
  let method = '';
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (input, init) => {
    url = String(input);
    method = init?.method || '';
    return Response.json({ deleted: true });
  };

  try {
    assert.deepEqual(await deleteReviewTask('task/a b'), { deleted: true });
    assert.equal(url, '/api/import/review-tasks/task%2Fa%20b');
    assert.equal(method, 'DELETE');
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('review client serializes reviewed question writes', async () => {
  let url = '';
  let method = '';
  let body = '';
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (input, init) => {
    url = String(input);
    method = init?.method || '';
    body = String(init?.body);
    return Response.json({ saved_count: 1 });
  };

  try {
    const payload = { task_id: 'task-1', questions: [] } as Parameters<typeof saveReviewedQuestions>[0];
    assert.deepEqual(await saveReviewedQuestions(payload), { saved_count: 1 });
    assert.equal(url, '/api/review/save');
    assert.equal(method, 'POST');
    assert.equal(body, JSON.stringify(payload));
  } finally {
    globalThis.fetch = originalFetch;
  }
});
