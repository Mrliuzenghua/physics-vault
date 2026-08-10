import assert from 'node:assert/strict';
import test from 'node:test';

import { batchUpdateMetadata, fetchQuestionKnowledgePoints } from './metadataApi.ts';

test('metadata client serializes batch update requests and returns the result', async () => {
  let url = '';
  let method = '';
  let body = '';
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (input, init) => {
    url = String(input);
    method = init?.method || '';
    body = String(init?.body);
    return Response.json({ updated: 2 });
  };

  try {
    const payload = {
      question_ids: ['q1', 'q2'],
      fields: ['knowledge_points'],
      mode: 'manual',
      force_overwrite: true,
    } as Parameters<typeof batchUpdateMetadata>[0];
    assert.deepEqual(await batchUpdateMetadata(payload), { updated: 2 });
    assert.equal(url, '/api/questions/batch-metadata');
    assert.equal(method, 'POST');
    assert.equal(body, JSON.stringify(payload));
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('metadata client encodes question IDs and preserves request failures', async () => {
  let url = '';
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (input) => {
    url = String(input);
    return new Response(JSON.stringify({ detail: 'knowledge unavailable' }), {
      status: 502,
      headers: { 'Content-Type': 'application/json' },
    });
  };

  try {
    await assert.rejects(() => fetchQuestionKnowledgePoints('question/a b'), /knowledge unavailable/);
    assert.equal(url, '/questions/question%2Fa%20b/knowledge-points');
  } finally {
    globalThis.fetch = originalFetch;
  }
});
