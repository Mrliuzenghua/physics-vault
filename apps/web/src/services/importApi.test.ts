import assert from 'node:assert/strict';
import test from 'node:test';

import { confirmImportBatch, createImportBatch, fetchImportBatchOverview } from './importApi.ts';

test('import client submits files through the batch endpoint', async () => {
  let url = '';
  let method = '';
  let body: BodyInit | null | undefined;
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (input, init) => {
    url = String(input);
    method = init?.method || '';
    body = init?.body;
    return Response.json({ batch_id: 'batch-1' });
  };

  try {
    assert.deepEqual(await createImportBatch(new File(['source'], 'physics.docx')), { batch_id: 'batch-1' });
    assert.equal(url, '/api/import/batches');
    assert.equal(method, 'POST');
    assert.ok(body instanceof FormData);
    assert.equal((body as FormData).get('file') instanceof File, true);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('import client normalizes an absent persisted batch list', async () => {
  let url = '';
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (input) => {
    url = String(input);
    return Response.json({});
  };

  try {
    assert.deepEqual(await fetchImportBatchOverview(8), []);
    assert.equal(url, '/api/import/batches?limit=8');
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('import client confirms the frozen batch content and version', async () => {
  let url = '';
  let body = '';
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (input, init) => {
    url = String(input);
    body = String(init?.body);
    return Response.json({ task_id: 'task-1', batch_id: 'batch-1', question_count: 1 });
  };
  try {
    assert.deepEqual(await confirmImportBatch('batch/a b', [{ title: '题目' }], 4), {
      task_id: 'task-1', batch_id: 'batch-1', question_count: 1,
    });
    assert.equal(url, '/api/import/batches/batch%2Fa%20b/confirm');
    assert.equal(body, JSON.stringify({ questions: [{ title: '题目' }], input_version: 4, media_assets: [] }));
  } finally {
    globalThis.fetch = originalFetch;
  }
});
