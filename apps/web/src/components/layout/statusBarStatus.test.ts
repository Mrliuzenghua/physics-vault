import assert from 'node:assert/strict';
import test from 'node:test';

import { resolveMcpServiceStatuses, resolveServiceStatus } from './statusBarStatus.ts';

test('keeps MCP services in checking state before a successful status poll', () => {
  const status = resolveServiceStatus(false, true, null);

  assert.equal(status.kind, 'checking');
  assert.equal(status.text, '检查中');
});

test('shows disabled runtime separately from offline providers', () => {
  const status = resolveServiceStatus(false, false, '2026-08-04T04:00:00.000Z');

  assert.equal(status.kind, 'disabled');
  assert.equal(status.text, '未启用');
});

test('reports online and offline only after runtime is enabled and checked', () => {
  const checkedAt = '2026-08-04T04:00:00.000Z';

  assert.equal(resolveServiceStatus(true, true, checkedAt).kind, 'online');
  assert.equal(resolveServiceStatus(false, true, checkedAt).kind, 'offline');
});

test('resolves VL and LLM independently from one runtime snapshot', () => {
  const statuses = resolveMcpServiceStatuses({
    enabled: true,
    vl_available: true,
    llm_available: false,
    last_checked_at: '2026-08-04T04:00:00.000Z',
  });

  assert.equal(statuses.vl.text, '在线');
  assert.equal(statuses.llm.text, '离线');
});
