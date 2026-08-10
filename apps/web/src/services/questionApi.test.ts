import assert from 'node:assert/strict';
import test from 'node:test';

import { deleteQuestions, fetchQuestionVersionDetail, searchQuestions } from './questionApi.ts';

test('question client serializes searches and preserves normalized list responses', async () => {
  let url = '';
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (input) => {
    url = String(input);
    return Response.json({ items: [], total: 0, limit: 5, offset: 0, search_mode: 'browse' });
  };

  try {
    assert.deepEqual(
      await searchQuestions({ query: '弹簧 / 受力', limit: 5, offset: 0, search_mode: 'browse' }),
      { items: [], total: 0, limit: 5, offset: 0, search_mode: 'browse' },
    );
    assert.match(url, /^\/search\/questions\?/);
    assert.match(url, /query=%E5%BC%B9%E7%B0%A7\+%2F\+%E5%8F%97%E5%8A%9B/);
    assert.match(url, /include_facets=false/);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('question client serializes batch deletes', async () => {
  let url = '';
  let method = '';
  let body = '';
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (input, init) => {
    url = String(input);
    method = init?.method || '';
    body = String(init?.body);
    return Response.json({ requested_count: 2, deleted_count: 2, missing_ids: [] });
  };

  try {
    assert.deepEqual(await deleteQuestions(['question-1', 'question-2']), {
      requested_count: 2,
      deleted_count: 2,
      missing_ids: [],
    });
    assert.equal(url, '/api/questions/batch-delete');
    assert.equal(method, 'POST');
    assert.equal(body, JSON.stringify({ question_ids: ['question-1', 'question-2'] }));
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('question client encodes version paths and preserves request failures', async () => {
  let url = '';
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (input) => {
    url = String(input);
    return new Response(JSON.stringify({ detail: 'version unavailable' }), {
      status: 503,
      headers: { 'Content-Type': 'application/json' },
    });
  };

  try {
    await assert.rejects(
      () => fetchQuestionVersionDetail('question/a b', 'version/1'),
      /version unavailable/,
    );
    assert.equal(url, '/questions/question%2Fa%20b/versions/version%2F1');
  } finally {
    globalThis.fetch = originalFetch;
  }
});
