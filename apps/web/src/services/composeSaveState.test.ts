import assert from 'node:assert/strict';
import test from 'node:test';

import { formatDraftSavedTime, getDraftSavePresentation } from './composeSaveState.ts';

test('presents idle, pending, saving, saved, and failed draft states consistently', () => {
  assert.equal(getDraftSavePresentation('idle', null, null).label, '等待编辑');
  assert.equal(getDraftSavePresentation('pending', null, null).label, '有未保存更改');
  assert.equal(getDraftSavePresentation('saving', null, null).label, '正在保存…');
  assert.match(getDraftSavePresentation('saved', '2026-08-12T14:25:00Z', null).label, /^已保存 /);
  assert.equal(getDraftSavePresentation('error', null, '网络不可用').title, '网络不可用');
});

test('ignores invalid saved timestamps', () => {
  assert.equal(formatDraftSavedTime('not-a-date'), null);
  assert.equal(getDraftSavePresentation('saved', 'not-a-date', null).label, '已保存');
});

test('formats revision timestamps that include a uniqueness suffix', () => {
  assert.match(formatDraftSavedTime('2026-08-12T14:27:51.706265+00:00-dd849b') || '', /^\d{2}:\d{2}$/);
});
