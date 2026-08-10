import assert from 'node:assert/strict';
import test from 'node:test';

import {
  buildReviewQueueCounts,
  filterReviewDrafts,
  findNextRiskIndex,
} from './reviewQueue.ts';
import type { ReviewQuestionDraft } from '../../types';

function draft(id: string, patch: Partial<ReviewQuestionDraft> = {}): ReviewQuestionDraft {
  return {
    question_id: id,
    question_type: 'calculation',
    title: `题目 ${id}`,
    options: [],
    answer: '答案',
    analysis: '',
    sub_questions: [],
    figures: [],
    difficulty: null,
    knowledge_point: '力学',
    knowledge_points: [],
    topic3_ids: [],
    topic1_id: '',
    topic1_name: '',
    topic2_id: '',
    topic2_name: '',
    topic3_id: '',
    topic3_name: '',
    tags: [],
    source: '测试',
    year: null,
    import_batch_id: undefined,
    source_page: null,
    source_region_id: null,
    source_bbox: null,
    raw_text: null,
    status: 'pending',
    figureIssues: [],
    ...patch,
  };
}

test('calculates review queue counts without mutating drafts', () => {
  const drafts = [draft('q1', { answer: '' }), draft('q2', { status: 'confirmed' })];
  const counts = buildReviewQueueCounts(drafts, new Set(), {}, 1);

  assert.equal(counts.total, 2);
  assert.equal(counts.pending, 1);
  assert.equal(counts.confirmed, 1);
  assert.equal(counts.missingAnswer, 1);
  assert.equal(counts.failedPage, 1);
  assert.equal(drafts[0]?.answer, '');
});

test('filters failed-page and text queues without changing drafts', () => {
  const drafts = [draft('q1', { source_page: 2 }), draft('q2', { title: '电场实验', source_page: 3 })];
  assert.deepEqual(
    filterReviewDrafts(drafts, 'ai_failed_page', '', new Set(), {}, [{ page_no: 2, status: 'failed' }]).map(({ draft: item }) => item.question_id),
    ['q1'],
  );
  assert.deepEqual(
    filterReviewDrafts(drafts, 'all', '实验', new Set(), {}, []).map(({ draft: item }) => item.question_id),
    ['q2'],
  );
});

test('uses one wrapping selector for the next risk item', () => {
  const drafts = [draft('q1', { answer: '' }), draft('q2'), draft('q3', { answer: '' })];

  assert.equal(findNextRiskIndex(drafts, 0, new Set(), {}), 2);
  assert.equal(findNextRiskIndex(drafts, 2, new Set(), {}), 0);
});
