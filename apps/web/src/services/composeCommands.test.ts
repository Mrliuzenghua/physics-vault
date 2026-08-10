import assert from 'node:assert/strict';
import test from 'node:test';

import {
  applyComposeCommands,
  parseComposeCommandsFromText,
  stripComposeCommandsFromText,
} from './composeCommands.ts';
import type { ComposeItem } from '../types';

const initialItems: ComposeItem[] = [
  {
    id: 'intro',
    type: 'text',
    title: 'Introduction',
    content: 'Original content',
  },
  {
    id: 'question-row',
    type: 'question',
    questionId: 'q-1',
    question: {
      question_id: 'q-1',
      question_type: 'single_choice',
      title: 'Original question',
      options: [{ opt: 'A', content: 'Option A' }],
      answer: 'A',
      analysis: '',
      sub_questions: [],
      figures: [{ fig_uuid: 'fig-1', local_path: 'figures/one.png', display_scale: 50 }],
      difficulty: 2,
      knowledge_point: '',
      knowledge_points: [],
      tags: [],
      source: '',
      review_status: 'approved',
    },
  },
];

test('parses only supported commands from a fenced response and strips that batch', () => {
  const text = [
    'I prepared two safe changes.',
    '```json',
    JSON.stringify({
      composeCommands: [
        { type: 'insert_text', title: 'Warm-up', content: 'Review vectors.' },
        { type: 'move_node', nodeId: 'intro', toIndex: 'not-a-number' },
        { type: 'set_all_figures', displayScale: 60 },
      ],
    }),
    '```',
    'Please review the result.',
  ].join('\n');

  assert.deepEqual(parseComposeCommandsFromText(text), [
    { type: 'insert_text', title: 'Warm-up', content: 'Review vectors.' },
    { type: 'set_all_figures', displayScale: 60 },
  ]);
  assert.equal(
    stripComposeCommandsFromText(text),
    'I prepared two safe changes.\n\nPlease review the result.',
  );
});

test('leaves prose unchanged when the embedded batch is invalid', () => {
  const text = 'Keep this explanation. {"composeCommands":[{"type":"remove_node"}]}';

  assert.deepEqual(parseComposeCommandsFromText(text), []);
  assert.equal(stripComposeCommandsFromText(text), text);
});

test('applies nested updates immutably and clamps figure scales at the command boundary', () => {
  const before = structuredClone(initialItems);
  const result = applyComposeCommands(initialItems, [
    { type: 'update_text', nodeId: 'intro', patch: { content: 'Updated content' } },
    { type: 'update_question', questionId: 'q-1', patch: { title: 'Updated question', question_id: 'wrong-id' } },
    { type: 'update_figure', questionId: 'q-1', figureId: 'fig-1', displayScale: 101, displayAlign: 'right', caption: 'Diagram' },
    { type: 'set_all_figures', displayScale: 12, displayAlign: 'left' },
  ]);

  assert.deepEqual(initialItems, before);
  assert.notEqual(result, initialItems);
  assert.notEqual(result[0], initialItems[0]);
  assert.notEqual(result[1], initialItems[1]);

  const text = result[0];
  const question = result[1];
  if (text.type !== 'text' || question.type !== 'question' || !question.question) throw new Error('expected updated compose items');
  assert.equal(text.content, 'Updated content');
  assert.equal(question.question.question_id, 'q-1');
  assert.equal(question.question.title, 'Updated question');
  assert.deepEqual(question.question.figures, [{
    fig_uuid: 'fig-1',
    local_path: 'figures/one.png',
    display_scale: 25,
    display_align: 'left',
    caption: 'Diagram',
  }]);
});

test('inserts at missing anchors and clamps moves without mutating the source order', () => {
  const result = applyComposeCommands(initialItems, [
    { type: 'insert_text', content: 'Appended', afterId: 'not-found' },
    { type: 'move_node', nodeId: 'question-row', toIndex: -10 },
    { type: 'move_node_after', nodeId: 'question-row', afterId: 'not-found' },
  ]);

  assert.deepEqual(initialItems.map((item) => item.id), ['intro', 'question-row']);
  assert.equal(result[0]?.id, 'intro');
  assert.equal(result[1]?.type, 'text');
  assert.match(result[1]?.id ?? '', /^ai-text-/);
  assert.equal(result.at(-1)?.type, 'question');
});
