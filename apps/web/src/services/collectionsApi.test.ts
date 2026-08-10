import assert from 'node:assert/strict';
import test from 'node:test';

import { fetchCollectionTree, fetchQuestionCollections } from './collectionsApi.ts';

test('collections client fetches the collection tree', async () => {
  let url = '';
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (input) => {
    url = String(input);
    return Response.json([]);
  };

  try {
    assert.deepEqual(await fetchCollectionTree(), []);
    assert.equal(url, '/api/collections/tree');
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('collections client encodes question identifiers and preserves request failures', async () => {
  let url = '';
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (input) => {
    url = String(input);
    return new Response(JSON.stringify({ detail: 'collection unavailable' }), {
      status: 500,
      headers: { 'Content-Type': 'application/json' },
    });
  };

  try {
    await assert.rejects(() => fetchQuestionCollections('question/a b'), /collection unavailable/);
    assert.equal(url, '/api/collections/questions/question%2Fa%20b');
  } finally {
    globalThis.fetch = originalFetch;
  }
});
