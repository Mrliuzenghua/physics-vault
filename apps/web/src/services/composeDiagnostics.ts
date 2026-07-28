import type { LessonPackage, Question } from '../types';

export interface ComposeDiagnosticWarning {
  level: 'info' | 'warning' | 'danger';
  message: string;
}

export interface ComposeDiagnosticReport {
  totalScore: number;
  averageDifficulty: number;
  knowledgeCount: number;
  missingAnswerCount: number;
  missingAnalysisCount: number;
  typeDistribution: Record<string, number>;
  difficultyDistribution: Record<string, number>;
  warnings: ComposeDiagnosticWarning[];
}

const SCORE_BY_TYPE: Record<string, number> = {
  single_choice: 5,
  multi_choice: 6,
  fill: 5,
  experiment: 10,
  calculation: 12,
};

const TYPE_LABELS: Record<string, string> = {
  single_choice: '单选',
  multi_choice: '多选',
  fill: '填空',
  experiment: '实验',
  calculation: '计算',
};

export function buildComposeDiagnostics(pkg: LessonPackage): ComposeDiagnosticReport {
  const questions = pkg.questions;
  const typeDistribution: Record<string, number> = {};
  const difficultyDistribution: Record<string, number> = {};
  const knowledgeSet = new Set<string>();
  const sourceCounts = new Map<string, number>();

  let totalScore = 0;
  let difficultySum = 0;
  let difficultyCount = 0;
  let missingAnswerCount = 0;
  let missingAnalysisCount = 0;

  for (const question of questions) {
    const type = question.question_type || 'unknown';
    typeDistribution[type] = (typeDistribution[type] || 0) + 1;
    totalScore += SCORE_BY_TYPE[type] || 5;

    const difficulty = normalizeDifficulty(question.difficulty);
    difficultyDistribution[difficulty.label] = (difficultyDistribution[difficulty.label] || 0) + 1;
    if (difficulty.value > 0) {
      difficultySum += difficulty.value;
      difficultyCount += 1;
    }

    for (const name of getKnowledgeNames(question)) {
      knowledgeSet.add(name);
    }

    if (!question.answer?.trim()) missingAnswerCount += 1;
    if (!question.analysis?.trim()) missingAnalysisCount += 1;

    const source = question.primary_paper_id || question.source;
    if (source) {
      sourceCounts.set(source, (sourceCounts.get(source) || 0) + 1);
    }
  }

  const averageDifficulty = difficultyCount > 0 ? Number((difficultySum / difficultyCount).toFixed(1)) : 0;
  const warnings = buildWarnings({
    questions,
    knowledgeCount: knowledgeSet.size,
    missingAnswerCount,
    missingAnalysisCount,
    averageDifficulty,
    sourceCounts,
    typeDistribution,
  });

  return {
    totalScore,
    averageDifficulty,
    knowledgeCount: knowledgeSet.size,
    missingAnswerCount,
    missingAnalysisCount,
    typeDistribution,
    difficultyDistribution,
    warnings,
  };
}

export function formatQuestionType(type: string): string {
  return TYPE_LABELS[type] || type || '未知';
}

function normalizeDifficulty(value: unknown): { label: string; value: number } {
  const num = Number(value);
  if (!Number.isFinite(num) || num <= 0) return { label: '未标注', value: 0 };
  if (num <= 2) return { label: '基础', value: num };
  if (num <= 4) return { label: '中档', value: num };
  return { label: '压轴', value: num };
}

function getKnowledgeNames(question: Question): string[] {
  const structured = (question.knowledge_points || [])
    .map((point) => point.topic3_name || point.topic2_name || point.topic1_name)
    .filter((name): name is string => Boolean(name?.trim()));
  const legacy = question.knowledge_point?.trim() ? [question.knowledge_point.trim()] : [];
  return [...structured, ...legacy];
}

function buildWarnings(params: {
  questions: Question[];
  knowledgeCount: number;
  missingAnswerCount: number;
  missingAnalysisCount: number;
  averageDifficulty: number;
  sourceCounts: Map<string, number>;
  typeDistribution: Record<string, number>;
}): ComposeDiagnosticWarning[] {
  const warnings: ComposeDiagnosticWarning[] = [];
  const questionCount = params.questions.length;

  if (questionCount === 0) {
    warnings.push({ level: 'info', message: '还没有加入题目。' });
    return warnings;
  }
  if (params.knowledgeCount < Math.min(3, questionCount)) {
    warnings.push({ level: 'warning', message: '知识点覆盖偏窄，建议补充不同考点。' });
  }
  if (!params.typeDistribution.calculation && !params.typeDistribution.experiment) {
    warnings.push({ level: 'warning', message: '缺少计算题或实验题，综合训练力度偏弱。' });
  }
  if (params.averageDifficulty >= 4.2) {
    warnings.push({ level: 'warning', message: '平均难度偏高，适合作为拔高卷。' });
  }
  if (params.averageDifficulty > 0 && params.averageDifficulty <= 2) {
    warnings.push({ level: 'info', message: '平均难度偏低，适合作为基础巩固。' });
  }
  if (params.missingAnswerCount > 0) {
    warnings.push({ level: 'danger', message: `${params.missingAnswerCount} 道题缺少答案。` });
  }
  if (params.missingAnalysisCount > 0) {
    warnings.push({ level: 'warning', message: `${params.missingAnalysisCount} 道题缺少解析。` });
  }

  const concentratedSource = Array.from(params.sourceCounts.entries()).find(([, count]) => count >= 4);
  if (concentratedSource) {
    warnings.push({ level: 'info', message: `来源“${concentratedSource[0]}”占比较高，可考虑混入其他来源。` });
  }

  return warnings;
}

