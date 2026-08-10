import assert from 'node:assert/strict';
import test from 'node:test';

import { fetchAssetList, fetchAvailableImages } from './assetsApi.ts';

test('assets client sends asset filters and parses the response', async () => {
  let url = '';
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (input) => {
    url = String(input);
    return Response.json({ assets: [], total: 0 });
  };

  try {
    const result = await fetchAssetList({ keyword: '力 学', page: 2, pageSize: 20 });
    assert.deepEqual(result, { assets: [], total: 0 });
    assert.match(url, /^\/api\/assets\?/);
    assert.match(url, /keyword=%E5%8A%9B\+%E5%AD%A6/);
    assert.match(url, /page=2/);
    assert.match(url, /page_size=20/);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('assets client encodes image search terms and preserves request failures', async () => {
  let url = '';
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (input) => {
    url = String(input);
    return new Response(JSON.stringify({ detail: 'asset service unavailable' }), {
      status: 503,
      headers: { 'Content-Type': 'application/json' },
    });
  };

  try {
    await assert.rejects(() => fetchAvailableImages('a/b c'), /asset service unavailable/);
    assert.equal(url, '/api/questions/images/available?keyword=a%2Fb%20c');
  } finally {
    globalThis.fetch = originalFetch;
  }
});
