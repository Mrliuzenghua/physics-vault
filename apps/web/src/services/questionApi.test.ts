import assert from 'node:assert/strict';
import test from 'node:test';

import {
  deleteQuestions,
  fetchFacets,
  fetchKnowledgePointCounts,
  fetchKnowledgePoints,
  fetchQuestion,
  fetchQuestionAssets,
  fetchQuestionKnowledgePoints,
  fetchQuestionVersionDetail,
  fetchQuestionVersions,
  rollbackQuestionVersion,
  searchQuestions,
  updateQuestionKnowledgePoints,
} from './questionApi.ts';

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
    assert.match(url, /^\/api\/search\/questions\?/);
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
    assert.equal(url, '/api/questions/question%2Fa%20b/versions/version%2F1');
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('question client uses canonical API paths for question resources', async () => {
  const originalFetch = globalThis.fetch;
  const requests: Array<{ url: string; method: string }> = [];
  globalThis.fetch = async (input, init) => {
    const url = String(input);
    requests.push({ url, method: init?.method || 'GET' });
    if (url.includes('/rollback')) return Response.json({ ok: true, message: 'restored' });
    if (url === '/api/questions/question%2F1') return Response.json({ question_id: 'question/1', title: '题目' });
    return Response.json([]);
  };

  try {
    await fetchFacets();
    await fetchQuestion('question/1');
    await fetchQuestionVersions('question/1');
    await fetchQuestionVersionDetail('question/1', 'version/1');
    await rollbackQuestionVersion('question/1', 'version/1');
    await fetchQuestionKnowledgePoints('question/1');
    await updateQuestionKnowledgePoints('question/1', []);
    await fetchKnowledgePoints();
    await fetchKnowledgePointCounts();
    await fetchQuestionAssets('question/1');

    assert.deepEqual(requests, [
      { url: '/api/filters/facets', method: 'GET' },
      { url: '/api/questions/question%2F1', method: 'GET' },
      { url: '/api/questions/question%2F1/versions', method: 'GET' },
      { url: '/api/questions/question%2F1/versions/version%2F1', method: 'GET' },
      { url: '/api/questions/question%2F1/versions/version%2F1/rollback', method: 'POST' },
      { url: '/api/questions/question%2F1/knowledge-points', method: 'GET' },
      { url: '/api/questions/question%2F1/knowledge-points', method: 'PUT' },
      { url: '/api/knowledge-points', method: 'GET' },
      { url: '/api/knowledge-points/counts', method: 'GET' },
      { url: '/api/questions/question%2F1/assets', method: 'GET' },
    ]);
  } finally {
    globalThis.fetch = originalFetch;
  }
});
