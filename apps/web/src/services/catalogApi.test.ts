import assert from 'node:assert/strict';
import test from 'node:test';

import { fetchDatabaseStatus, fetchPaperQuestions } from './catalogApi.ts';

test('catalog client uses dedicated database and paper endpoints', async () => {
  const urls: string[] = [];
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (input) => {
    urls.push(String(input));
    return Response.json(urls.length === 1 ? { questions_count: 24 } : []);
  };
  try {
    assert.deepEqual(await fetchDatabaseStatus(), { questions_count: 24 });
    assert.deepEqual(await fetchPaperQuestions('paper/a b'), []);
    assert.deepEqual(urls, ['/api/system/db-status', '/papers/paper%2Fa%20b/questions']);
  } finally {
    globalThis.fetch = originalFetch;
  }
});
