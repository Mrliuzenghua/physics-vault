import assert from 'node:assert/strict';
import test from 'node:test';

import {
  fetchReviewDraftVersions,
  ReviewDraftConflictError,
  saveReviewDraft,
} from './reviewDraftApi.ts';

test('review draft client encodes task IDs and returns version history', async () => {
  let url = '';
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (input) => {
    url = String(input);
    return Response.json({ items: [], total: 0 });
  };

  try {
    assert.deepEqual(await fetchReviewDraftVersions('task/a b', 12), { items: [], total: 0 });
    assert.equal(url, '/api/review/drafts/task%2Fa%20b/versions?limit=12');
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('review draft client exposes the server draft on a version conflict', async () => {
  let url = '';
  let body = '';
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (input, init) => {
    url = String(input);
    body = String(init?.body);
    return Response.json({ detail: { current: { task_id: 'task-1', version: 3 } } }, { status: 409 });
  };

  try {
    await assert.rejects(
      () => saveReviewDraft('task-1', { base_version: 2, state: {} } as Parameters<typeof saveReviewDraft>[1]),
      (error: unknown) => error instanceof ReviewDraftConflictError && error.current?.version === 3,
    );
    assert.equal(url, '/api/review/drafts/task-1');
    assert.equal(body, JSON.stringify({ base_version: 2, state: {} }));
  } finally {
    globalThis.fetch = originalFetch;
  }
});
