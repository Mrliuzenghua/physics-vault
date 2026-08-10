import assert from 'node:assert/strict';
import test from 'node:test';

import { createAnnotation, fetchAnnotations } from './annotationsApi.ts';

test('annotations client encodes question IDs and returns annotation lists', async () => {
  let url = '';
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (input) => {
    url = String(input);
    return Response.json([]);
  };

  try {
    assert.deepEqual(await fetchAnnotations('question/a b'), []);
    assert.equal(url, '/api/questions/question%2Fa%20b/annotations');
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('annotations client serializes creates and preserves request failures', async () => {
  let method = '';
  let body = '';
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (_input, init) => {
    method = init?.method || '';
    body = String(init?.body);
    return new Response(JSON.stringify({ detail: 'annotation unavailable' }), {
      status: 503,
      headers: { 'Content-Type': 'application/json' },
    });
  };

  try {
    await assert.rejects(
      () => createAnnotation('question-1', { content: 'note', annotation_type: 'text' }),
      /annotation unavailable/,
    );
    assert.equal(method, 'POST');
    assert.equal(body, JSON.stringify({ content: 'note', annotation_type: 'text' }));
  } finally {
    globalThis.fetch = originalFetch;
  }
});
