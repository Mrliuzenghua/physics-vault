import assert from 'node:assert/strict';
import test from 'node:test';

import { fetchQuestionImageCache } from './imageCacheApi.ts';

test('image cache client encodes keyword searches', async () => {
  let url = '';
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (input) => {
    url = String(input);
    return Response.json([]);
  };
  try {
    assert.deepEqual(await fetchQuestionImageCache(' 弹簧 / 图 ', 8), []);
    assert.equal(url, '/api/questions/images/cache?limit=8&keyword=%E5%BC%B9%E7%B0%A7+%2F+%E5%9B%BE');
  } finally {
    globalThis.fetch = originalFetch;
  }
});
