import assert from 'node:assert/strict';
import test from 'node:test';

import {
  applyAiPatch,
  getChangedReviewFields,
  normalizeDraft,
  normalizeKnowledgeDraft,
  normalizeSourceBBox,
} from './reviewDraft.ts';

test('normalizes incomplete question drafts with safe defaults', () => {
  const draft = normalizeDraft({
    stem: '在实验中，按①连接电路\n②记录数据',
    question_type: 'single_choice',
    status: 'unknown',
    options: [{ opt: 'A', content: '$$F=ma$$' }, null],
    source_bbox: [1, '2', 3, 4],
  }, 2);

  assert.equal(draft.question_id, 'draft-3');
  assert.equal(draft.question_type, 'experiment');
  assert.equal(draft.status, 'pending');
  assert.deepEqual(draft.options, [{ opt: 'A', content: '$$F=ma$$' }]);
  assert.deepEqual(draft.source_bbox, [1, 2, 3, 4]);
});

test('rejects invalid source regions and normalizes knowledge draft fallbacks', () => {
  assert.equal(normalizeSourceBBox([1, 2, Infinity, 4]), null);
  assert.equal(normalizeSourceBBox([1, 2, 3]), null);

  const draft = normalizeKnowledgeDraft({ name: '牛顿第二定律', content: '$$F=ma$$', status: 'invalid' }, 0);
  assert.equal(draft.draft_id, 'knowledge-draft-1');
  assert.equal(draft.topic3_name, '牛顿第二定律');
  assert.equal(draft.definition, '$$F=ma$$');
  assert.equal(draft.status, 'pending');
});

test('treats non-JSON AI output as analysis and constrains supported JSON fields', () => {
  assert.deepEqual(applyAiPatch('不是 JSON 的 AI 输出 $$v=at$$'), {
    analysis: '不是 JSON 的 AI 输出 $v=at$',
  });

  assert.deepEqual(applyAiPatch('{"difficulty": 9, "options": [{"opt":"A","content":"$$x$$"}]}'), {
    difficulty: 5,
    options: [{ opt: 'A', content: '$$x$$' }],
  });
});

test('reports only the supported changed review fields', () => {
  const original = normalizeDraft({ question_id: 'q-1', title: '题干', answer: 'A', tags: ['力学'] }, 0);
  const updated = { ...original, answer: 'B', tags: ['力学', '运动'] };

  assert.deepEqual(getChangedReviewFields(original, updated), ['answer', 'tags']);
});
