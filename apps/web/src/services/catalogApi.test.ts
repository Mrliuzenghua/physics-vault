import assert from 'node:assert/strict';
import test from 'node:test';

import {
  fetchCatalogHealth,
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
    const url = String(input);
    urls.push(url);
    if (url === '/api/system/db-status') return Response.json({ questions_count: 25, browsable_questions_count: 24 });
    if (url === '/api/system/catalog-health') return Response.json({ total_questions: 24, healthy_questions: 20, questions_needing_attention: 4, score: 83, archived_duplicate_count: 1, issues: [] });
    if (url === '/api/system/health') return Response.json({ status: 'ok' });
    return Response.json([]);
  };
  try {
    assert.deepEqual(await fetchDatabaseStatus(), { questions_count: 25, browsable_questions_count: 24 });
    assert.deepEqual(await fetchCatalogHealth(), { total_questions: 24, healthy_questions: 20, questions_needing_attention: 4, score: 83, archived_duplicate_count: 1, issues: [] });
    assert.deepEqual(await fetchImages({ q: 'force diagram' }), []);
    assert.deepEqual(await fetchPapers(), []);
    assert.deepEqual(await fetchPaperQuestions('paper/a b'), []);
    assert.deepEqual(await fetchReviewQueue(), []);
    assert.deepEqual(await fetchEmbeddingStatus(), []);
    assert.deepEqual(await healthCheck(), { status: 'ok' });
    assert.deepEqual(urls, [
      '/api/system/db-status',
      '/api/system/catalog-health',
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
