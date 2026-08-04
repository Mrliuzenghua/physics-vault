import assert from 'node:assert/strict';
import test from 'node:test';

import {
  analyzeQuestionQuality,
  buildSafeQuestionPatch,
  findDuplicateQuestionIds,
  scoreQuestionQuality,
  type QualityQuestion,
} from './questionQuality.ts';

function question(patch: Partial<QualityQuestion> = {}): QualityQuestion {
  return {
    question_type: 'single_choice',
    title: '如图所示，物体做匀速直线运动，以下说法正确的是？',
    options: [
      { opt: 'A', content: '速度保持不变' },
      { opt: 'B', content: '加速度不断增大' },
    ],
    answer: 'A',
    analysis: '匀速直线运动的速度大小和方向均不变。',
    figures: [],
    knowledge_point: '匀速直线运动',
    source: '测试题',
    ...patch,
  };
}

test('reports structural errors and answer-option mismatch', () => {
  const issues = analyzeQuestionQuality(question({ title: '', answer: 'C', options: [] }), {
    requireKnowledge: true,
    requireSource: true,
  });
  assert.deepEqual(issues.map((item) => item.code), ['empty_title', 'missing_options', 'answer_option_mismatch']);
});

test('supports disabling rules and overriding severity', () => {
  const issues = analyzeQuestionQuality(question({ answer: '' }), {
    config: {
      enabled: { missing_answer: false },
      severity: { missing_source: 'danger' },
    },
    requireSource: true,
  });
  assert.equal(issues.some((item) => item.code === 'missing_answer'), false);

  const sourceIssues = analyzeQuestionQuality(question({ source: '' }), {
    config: { severity: { missing_source: 'danger' } },
    requireSource: true,
  });
  assert.equal(sourceIssues.find((item) => item.code === 'missing_source')?.severity, 'danger');
});

test('uses configurable minimum option count and penalties', () => {
  const issues = analyzeQuestionQuality(question(), { config: { minimumChoiceOptions: 4 } });
  assert.equal(issues.find((item) => item.code === 'too_few_options')?.message, '选择题选项少于 4 个');
  assert.equal(scoreQuestionQuality(issues, { penalties: { warning: 9 } }), 91);
});

test('detects duplicate questions after punctuation normalization', () => {
  const first = question();
  const second = question({ title: '如图所示，物体做匀速直线运动；以下说法正确的是？' });
  const ids = findDuplicateQuestionIds(
    [{ id: 'q1', ...first }, { id: 'q2', ...second }],
    (item) => item.id,
  );
  assert.deepEqual([...ids].sort(), ['q1', 'q2']);
});

test('safe cleanup normalizes whitespace and option labels', () => {
  const patch = buildSafeQuestionPatch(question({
    title: '  题干  \n\n\n\n第二段  ',
    options: [{ opt: 'X', content: ' 甲  ' }, { opt: 'Y', content: '乙' }],
  }));
  assert.equal(patch.title, '题干\n\n第二段');
  assert.deepEqual(patch.options.map((item) => item.opt), ['A', 'B']);
});

test('accepts figure references outside the stem', () => {
  const figures = [{ fig_uuid: 'fig-analysis', local_path: 'batch/media/a.png' }];
  for (const patch of [
    { options: [{ opt: 'A', content: '见图 ![fig:fig-analysis]' }, { opt: 'B', content: '无' }] },
    { answer: '参考 ![fig:fig-analysis]' },
    { analysis: '解析图 ![fig:fig-analysis]' },
  ]) {
    const issues = analyzeQuestionQuality(question({ figures, ...patch }));
    assert.equal(issues.some((item) => item.code === 'image_issue'), false);
  }
});
