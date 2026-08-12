import assert from 'node:assert/strict';
import test from 'node:test';

import {
  fetchDatabaseStatus,
  fetchEmbeddingStatus,
  fetchImages,
  fetchPaperQuestions,
  fetchPapers,
  fetchReviewQueue,
  healthCheck,
} from './catalogApi.ts';

test('catalog client uses canonical API endpoints', async () => {
  const urls: string[] = [];
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (input) => {
    urls.push(String(input));
    return Response.json(urls.length === 1 ? { questions_count: 25, browsable_questions_count: 24 } : urls.length === 7 ? { status: 'ok' } : []);
  };
  try {
    assert.deepEqual(await fetchDatabaseStatus(), { questions_count: 25, browsable_questions_count: 24 });
    assert.deepEqual(await fetchImages({ q: 'force diagram' }), []);
    assert.deepEqual(await fetchPapers(), []);
    assert.deepEqual(await fetchPaperQuestions('paper/a b'), []);
    assert.deepEqual(await fetchReviewQueue(), []);
    assert.deepEqual(await fetchEmbeddingStatus(), []);
    assert.deepEqual(await healthCheck(), { status: 'ok' });
    assert.deepEqual(urls, [
      '/api/system/db-status',
      '/api/images?q=force+diagram',
      '/api/papers',
      '/api/papers/paper%2Fa%20b/questions',
      '/api/review-queue',
      '/api/embeddings/status',
      '/api/system/health',
    ]);
  } finally {
    globalThis.fetch = originalFetch;
  }
});
