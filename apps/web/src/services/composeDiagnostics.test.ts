import assert from 'node:assert/strict';
import test from 'node:test';

import { buildComposeDiagnostics, formatQuestionType } from './composeDiagnostics.ts';
import type { LessonPackage, Question } from '../types';

function question(overrides: Partial<Question> = {}): Question {
  return {
    question_id: 'q-1',
    question_type: 'single_choice',
    title: 'A complete question',
    options: [
      { opt: 'A', content: 'First option' },
      { opt: 'B', content: 'Second option' },
    ],
    answer: 'A',
    analysis: 'A complete analysis.',
    sub_questions: [],
    figures: [],
    difficulty: 2,
    knowledge_point: 'Kinematics',
    knowledge_points: [],
    tags: [],
    source: 'Source A',
    review_status: 'approved',
    ...overrides,
  };
}

function lessonPackage(questions: Question[]): LessonPackage {
  return {
    id: 'lesson-1',
    title: 'Practice',
    subtitle: '',
    source: 'compose',
    questions,
    knowledgeCards: [],
    textBlocks: [],
    nodes: [],
    createdAt: '',
    updatedAt: '',
  };
}

test('reports an empty lesson without inventing diagnostics', () => {
  const report = buildComposeDiagnostics(lessonPackage([]));

  assert.equal(report.totalScore, 0);
  assert.equal(report.averageDifficulty, 0);
  assert.equal(report.knowledgeCount, 0);
  assert.deepEqual(report.typeDistribution, {});
  assert.deepEqual(report.difficultyDistribution, {});
  assert.deepEqual(report.warnings.map((warning) => warning.level), ['info']);
});

test('aggregates score, quality gaps, distributions, and per-question risks', () => {
  const report = buildComposeDiagnostics(lessonPackage([
    question({
      question_id: 'q-choice',
      knowledge_points: [{
        rank: 3,
        topic1_id: 'mechanics',
        topic1_name: 'Mechanics',
        topic2_id: 'motion',
        topic2_name: 'Motion',
        topic3_id: 'kinematics',
        topic3_name: 'Kinematics',
      }],
    }),
    question({
      question_id: 'q-calculation',
      question_type: 'calculation',
      title: 'Compute $F',
      options: [],
      answer: '',
      analysis: '',
      difficulty: 5,
      knowledge_point: 'Dynamics',
      knowledge_points: [],
      source: 'Source B',
    }),
    question({
      question_id: 'q-experiment',
      question_type: 'experiment',
      title: 'Observe ![fig:missing-figure]',
      difficulty: 3,
      knowledge_point: 'Electricity',
      knowledge_points: [],
      source: 'Source C',
    }),
  ]));

  assert.equal(report.totalScore, 27);
  assert.equal(report.averageDifficulty, 3.3);
  assert.equal(report.knowledgeCount, 3);
  assert.equal(report.missingAnswerCount, 1);
  assert.equal(report.missingAnalysisCount, 1);
  assert.equal(report.formulaIssueCount, 1);
  assert.equal(report.figureIssueCount, 2);
  assert.equal(report.proofreadingIssueCount, 0);
  assert.deepEqual(report.typeDistribution, {
    single_choice: 1,
    calculation: 1,
    experiment: 1,
  });
  assert.equal(Object.values(report.difficultyDistribution).reduce((sum, count) => sum + count, 0), 3);

  const risksByQuestion = report.warnings
    .filter((warning) => warning.questionId)
    .map((warning) => `${warning.questionId}:${warning.code}`)
    .sort();
  assert.deepEqual(risksByQuestion, [
    'q-calculation:formula',
    'q-experiment:figure',
  ]);
});

test('formats known types while preserving unknown type identifiers', () => {
  assert.notEqual(formatQuestionType('single_choice'), 'single_choice');
  assert.equal(formatQuestionType('custom_type'), 'custom_type');
  assert.notEqual(formatQuestionType(''), '');
});
