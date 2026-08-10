import assert from 'node:assert/strict';
import test from 'node:test';

import { createImportBatch, fetchImportBatchOverview } from './importApi.ts';

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
