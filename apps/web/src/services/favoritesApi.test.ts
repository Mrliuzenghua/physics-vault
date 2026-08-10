import assert from 'node:assert/strict';
import test from 'node:test';

import { fetchFavoriteGroups, fetchFavoriteItem } from './favoritesApi.ts';

test('favorites client fetches a group list', async () => {
  let url = '';
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (input) => {
    url = String(input);
    return Response.json([{ id: 'group-1', name: '重点' }]);
  };

  try {
    assert.deepEqual(await fetchFavoriteGroups(), [{ id: 'group-1', name: '重点' }]);
    assert.equal(url, '/api/favorites/groups');
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('favorites client encodes item identifiers and preserves request failures', async () => {
  let url = '';
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (input) => {
    url = String(input);
    return new Response(JSON.stringify({ detail: 'favorite unavailable' }), {
      status: 502,
      headers: { 'Content-Type': 'application/json' },
    });
  };

  try {
    await assert.rejects(() => fetchFavoriteItem('question/a b'), /favorite unavailable/);
    assert.equal(url, '/api/favorites/items/question%2Fa%20b');
  } finally {
    globalThis.fetch = originalFetch;
  }
});
