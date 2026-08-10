import assert from 'node:assert/strict';
import test from 'node:test';

import { buildComposeItemsFromPaperDraft } from './composeDraft.ts';

const sourceQuestion = {
  question_id: 'q-1',
  question_type: 'single_choice' as const,
  title: '题库原题',
  options: [{ opt: 'A', content: '原选项' }],
  answer: 'A',
  analysis: '原解析',
  sub_questions: [],
  figures: [],
  difficulty: 2,
  knowledge_point: '力学',
  knowledge_points: [],
  tags: [],
  source: '题库',
  review_status: 'approved' as const,
};

test('restores an edited project question from its snapshot', () => {
  const items = buildComposeItemsFromPaperDraft({
    id: 'draft-1',
    title: '练习',
    subtitle: '',
    source: 'compose',
    status: 'draft',
    question_count: 1,
    item_count: 1,
    total_score: 5,
    created_at: '',
    updated_at: '',
    items: [{
      id: 'instance-1',
      type: 'question',
      position: 0,
      question_id: 'q-1',
      payload: {
        question_snapshot: {
          ...sourceQuestion,
          title: '项目内修改后的题干',
          options: [{ opt: 'A', content: '项目内选项' }],
          analysis: '项目内解析',
        },
      },
    }],
    metadata: {},
    quality_report: {},
  }, [sourceQuestion]);

  if (items[0]?.type !== 'question') throw new Error('expected a question item');
  assert.equal(items[0].question?.title, '项目内修改后的题干');
  assert.equal(items[0].question?.options[0]?.content, '项目内选项');
  assert.equal(items[0].question?.analysis, '项目内解析');
});

test('falls back to the question bank for legacy drafts without snapshots', () => {
  const items = buildComposeItemsFromPaperDraft({
    id: 'legacy-draft',
    title: '旧草稿',
    subtitle: '',
    source: 'compose',
    status: 'draft',
    question_count: 1,
    item_count: 1,
    total_score: 5,
    created_at: '',
    updated_at: '',
    items: [{ id: 'q-1', type: 'question', position: 0, question_id: 'q-1', payload: {} }],
    metadata: {},
    quality_report: {},
  }, [sourceQuestion]);

  if (items[0]?.type !== 'question') throw new Error('expected a question item');
  assert.equal(items[0].question?.title, '题库原题');
});
