import assert from 'node:assert/strict';
import test from 'node:test';

import { fetchMcpStatus, streamQuestionPickerAgent } from './aiApi.ts';

test('AI client requests the MCP runtime status', async () => {
  let url = '';
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (input) => {
    url = String(input);
    return Response.json({ enabled: true });
  };
  try {
    assert.deepEqual(await fetchMcpStatus(), { enabled: true });
    assert.equal(url, '/api/mcp/status');
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('AI client decodes newline-delimited streaming agent events', async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => new Response(new ReadableStream({
    start(controller) {
      controller.enqueue(new TextEncoder().encode('{"type":"message","content":"first"}\n{"type":"done"}'));
      controller.close();
    },
  }));
  const events: unknown[] = [];
  try {
    await streamQuestionPickerAgent([], { onEvent: (event) => events.push(event) });
    assert.deepEqual(events, [{ type: 'message', content: 'first' }, { type: 'done' }]);
  } finally {
    globalThis.fetch = originalFetch;
  }
});
