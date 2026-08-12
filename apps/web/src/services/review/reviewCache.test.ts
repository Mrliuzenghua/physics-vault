import assert from 'node:assert/strict';
import test from 'node:test';

import {
  clearReviewCache,
  mediaAssetsFromDrafts,
  mergeMediaAssets,
  mergeTaskMeta,
  readQualityConfig,
  readReviewCache,
  writeQualityConfig,
  writeReviewCache,
} from './reviewCache.ts';
import type { ReviewQuestionDraft } from '../../types';

class MemoryStorage {
  private readonly values = new Map<string, string>();

  getItem(key: string): string | null { return this.values.get(key) ?? null; }
  setItem(key: string, value: string): void { this.values.set(key, value); }
  removeItem(key: string): void { this.values.delete(key); }
}

function withStorage(storage: Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>, run: () => void): void {
  const original = globalThis.window;
  Object.defineProperty(globalThis, 'window', { configurable: true, value: { localStorage: storage } });
  try {
    run();
  } finally {
    Object.defineProperty(globalThis, 'window', { configurable: true, value: original });
  }
}

function draftWithFigure(localPath: string, figUuid = 'fig-1'): ReviewQuestionDraft {
  return { figures: [{ fig_uuid: figUuid, local_path: localPath }] } as ReviewQuestionDraft;
}

test('ignores damaged review cache and preserves the task id boundary', () => {
  const storage = new MemoryStorage();
  withStorage(storage, () => {
    storage.setItem('physics_vault_review_cache.task-1', '{invalid');
    assert.equal(readReviewCache('task-1'), null);

    writeReviewCache('task-1', {
      drafts: [],
      taskMeta: { warnings: [], pageResults: [], mediaAssets: [] },
      currentIndex: 0,
      queue: 'risk',
    });
    assert.equal(readReviewCache('task-1')?.taskId, 'task-1');
    assert.equal(readReviewCache('task-2'), null);
    clearReviewCache('task-1');
    assert.equal(readReviewCache('task-1'), null);
  });
});

test('keeps working when browser storage is unavailable', () => {
  const original = globalThis.window;
  Object.defineProperty(globalThis, 'window', { configurable: true, value: { get localStorage(): Storage { throw new Error('blocked'); } } });
  try {
    assert.deepEqual(readQualityConfig(), {});
    assert.doesNotThrow(() => writeQualityConfig({ minimumChoiceOptions: 4 }));
    assert.equal(readReviewCache('blocked-task'), null);
    assert.doesNotThrow(() => writeReviewCache('blocked-task', {
      drafts: [],
      taskMeta: { warnings: [], pageResults: [], mediaAssets: [] },
      currentIndex: 0,
      queue: 'risk',
    }));
    assert.doesNotThrow(() => clearReviewCache('blocked-task'));
  } finally {
    Object.defineProperty(globalThis, 'window', { configurable: true, value: original });
  }
});

test('deduplicates media by stable path and retains draft figures during metadata merge', () => {
  const first = { image_id: 'one', filename: 'one.png', relative_path: 'media/one.png', absolute_path: '', size: 1 };
  const duplicate = { ...first, image_id: 'duplicate' };
  assert.deepEqual(mergeMediaAssets([first], [duplicate]), [first]);
  assert.deepEqual(mediaAssetsFromDrafts([draftWithFigure('media/two.png', 'two')]).map((asset) => asset.relative_path), ['media/two.png']);

  const meta = mergeTaskMeta(
    { warnings: ['local'], pageResults: [], mediaAssets: [first] },
    { batchId: 'batch-1', warnings: ['remote'], pageResults: [], mediaAssets: [duplicate] },
    [draftWithFigure('media/two.png', 'two')],
  );
  assert.deepEqual(meta.mediaAssets.map((asset) => asset.relative_path), ['media/one.png', 'media/two.png']);
  assert.deepEqual(meta.warnings, ['local']);
});
