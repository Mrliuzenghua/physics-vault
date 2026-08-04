import assert from 'node:assert/strict';
import test from 'node:test';

import { request, requestForm } from './apiClient.ts';

test('request adds JSON content type and returns parsed data', async () => {
  let captured: RequestInit | undefined;
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (_input, init) => {
    captured = init;
    return new Response(JSON.stringify({ ok: true }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    });
  };

  try {
    const result = await request<{ ok: boolean }>('/example', {
      method: 'POST',
      body: JSON.stringify({ value: 1 }),
    });
    assert.deepEqual(result, { ok: true });
    assert.equal(new Headers(captured?.headers).get('Content-Type'), 'application/json');
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('requestForm leaves the multipart content type to the browser', async () => {
  let captured: RequestInit | undefined;
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (_input, init) => {
    captured = init;
    return new Response(JSON.stringify({ uploaded: true }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    });
  };

  try {
    const form = new FormData();
    form.append('file', new Blob(['content']), 'example.txt');
    const result = await requestForm<{ uploaded: boolean }>('/upload', form);
    assert.deepEqual(result, { uploaded: true });
    assert.equal(new Headers(captured?.headers).has('Content-Type'), false);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('request exposes the server detail message on failure', async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => new Response(
    JSON.stringify({ detail: { message: '题库写入失败' } }),
    { status: 409, headers: { 'Content-Type': 'application/json' } },
  );

  try {
    await assert.rejects(() => request('/example'), /题库写入失败/);
  } finally {
    globalThis.fetch = originalFetch;
  }
});
