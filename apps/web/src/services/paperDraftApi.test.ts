import assert from 'node:assert/strict';
import test from 'node:test';

import { fetchPaperDraft, listPaperDrafts } from './paperDraftApi.ts';

test('paper draft client bounds list requests through the dedicated endpoint', async () => {
  let url = '';
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (input) => {
    url = String(input);
    return Response.json({ items: [] });
  };
  try {
    assert.deepEqual(await listPaperDrafts(12), { items: [] });
    assert.equal(url, '/api/paper-drafts?limit=12');
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('paper draft client treats a missing draft as absent', async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => new Response(JSON.stringify({ detail: 'not found' }), {
    status: 404, headers: { 'Content-Type': 'application/json' },
  });
  try {
    assert.equal(await fetchPaperDraft('draft/a b'), null);
  } finally {
    globalThis.fetch = originalFetch;
  }
});
