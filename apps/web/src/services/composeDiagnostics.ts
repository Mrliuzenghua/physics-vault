import type { LessonPackage, Question } from '../types';

export interface ComposeDiagnosticWarning {
  level: 'info' | 'warning' | 'danger';
  message: string;
  questionId?: string;
  code?: 'formula' | 'figure' | 'answer' | 'analysis' | 'proofreading';
}

export interface ComposeDiagnosticReport {
  totalScore: number;
  averageDifficulty: number;
  knowledgeCount: number;
  missingAnswerCount: number;
  missingAnalysisCount: number;
  formulaIssueCount: number;
  figureIssueCount: number;
  proofreadingIssueCount: number;
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
  let formulaIssueCount = 0;
  let figureIssueCount = 0;
  let proofreadingIssueCount = 0;

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
    formulaIssueCount += detectFormulaIssues(question).length;
    figureIssueCount += detectFigureIssues(question).length;
    proofreadingIssueCount += detectProofreadingIssues(question).length;

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
    formulaIssueCount,
    figureIssueCount,
    proofreadingIssueCount,
    averageDifficulty,
    sourceCounts,
    typeDistribution,
  });
  for (const question of questions) {
    const formulaIssues = detectFormulaIssues(question);
    const figureIssues = detectFigureIssues(question);
    if (formulaIssues.length > 0) warnings.push({
      level: 'danger',
      code: 'formula',
      questionId: question.question_id,
      message: `${question.question_id}：${formulaIssues[0]}`,
    });
    if (figureIssues.length > 0) warnings.push({
      level: 'danger',
      code: 'figure',
      questionId: question.question_id,
      message: `${question.question_id}：${figureIssues[0]}`,
    });
  }

  return {
    totalScore,
    averageDifficulty,
    knowledgeCount: knowledgeSet.size,
    missingAnswerCount,
    missingAnalysisCount,
    formulaIssueCount,
    figureIssueCount,
    proofreadingIssueCount,
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
  formulaIssueCount: number;
  figureIssueCount: number;
  proofreadingIssueCount: number;
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
  if (params.formulaIssueCount > 0) {
    warnings.push({ level: 'danger', message: `${params.formulaIssueCount} 处公式疑似未正确渲染。` });
  }
  if (params.figureIssueCount > 0) {
    warnings.push({ level: 'danger', message: `${params.figureIssueCount} 处图片占位或配图异常。` });
  }
  if (params.proofreadingIssueCount > 0) {
    warnings.push({ level: 'warning', message: `${params.proofreadingIssueCount} 处选项/答案/文本格式需要校对。` });
  }

  const concentratedSource = Array.from(params.sourceCounts.entries()).find(([, count]) => count >= 4);
  if (concentratedSource) {
    warnings.push({ level: 'info', message: `来源“${concentratedSource[0]}”占比较高，可考虑混入其他来源。` });
  }

  return warnings;
}

function collectQuestionText(question: Question): string {
  return [
    question.title,
    question.stem_text,
    ...(question.options || []).map((option) => `${option.opt}. ${option.content}`),
    question.answer,
    question.analysis,
  ].filter(Boolean).join('\n');
}

function detectFormulaIssues(question: Question): string[] {
  const text = collectQuestionText(question);
  const issues: string[] = [];
  const dollarCount = (text.match(/\$/g) || []).length;
  if (dollarCount % 2 === 1) issues.push('公式分隔符数量异常');
  if (/\\?mspace\s*\{?\s*-?\d+(?:\.\d+)?\s*(?:mu|em|pt)\s*\}?/i.test(text)) issues.push('存在 mspace 残留');
  if (/\\(?:frac|sqrt|left|right|over|times|cdot)\b(?![\s{\\])/i.test(text)) issues.push('LaTeX 命令可能缺少参数');
  const proseOnly = text
    .replace(/\$\$[\s\S]*?\$\$/g, '')
    .replace(/\$[^$\n]+\$/g, '')
    .replace(/\\\[[\s\S]*?\\\]/g, '')
    .replace(/\\\([^\n]*?\\\)/g, '');
  if (/\\(?:frac|dfrac|tfrac|sqrt|times|cdot|theta|lambda|mu|Delta)\b|\b[A-Za-z]+_[A-Za-z0-9]+\b/.test(proseOnly)) {
    issues.push('存在未放入公式标记的 LaTeX 内容');
  }
  return issues;
}

function detectFigureIssues(question: Question): string[] {
  const text = `${question.title || ''}\n${question.stem_text || ''}`;
  const refs = Array.from(text.matchAll(/!\[fig:([^\]]+)\]/g)).map((match) => match[1]);
  const figures = question.figures || [];
  const figureIds = new Set(figures.map((figure) => figure.fig_uuid).filter(Boolean));
  const issues: string[] = [];

  for (const ref of refs) {
    if (!figureIds.has(ref)) issues.push(`缺少图片 ${ref}`);
  }
  for (const figure of figures) {
    if (!figure.local_path) issues.push(`图片 ${figure.fig_uuid || ''} 缺少文件路径`);
    if (figure.display_scale != null && (!Number.isFinite(Number(figure.display_scale)) || Number(figure.display_scale) < 25 || Number(figure.display_scale) > 100)) {
      issues.push(`图片 ${figure.fig_uuid || ''} 显示比例超出 25%–100%`);
    }
  }
  if (refs.length > 0 && figures.length === 0) issues.push('题干含图片占位符但没有配图');
  return issues;
}

function detectProofreadingIssues(question: Question): string[] {
  const issues: string[] = [];
  const options = question.options || [];
  const labels = options.map((option) => option.opt?.trim()).filter(Boolean);
  const expectedLabels = options.map((_, index) => String.fromCharCode(65 + index));
  if (labels.length > 0 && labels.some((label, index) => label !== expectedLabels[index])) {
    issues.push('选项编号不连续');
  }
  const answer = question.answer?.trim();
  if (answer && options.length > 0) {
    const answerLetters = Array.from(answer.matchAll(/[A-H]/g)).map((match) => match[0]);
    if (answerLetters.length > 0 && answerLetters.some((letter) => !labels.includes(letter))) {
      issues.push('答案不在选项中');
    }
  }
  if (/[A-Za-z]\s{2,}[A-Za-z]|\d\s{2,}\d/.test(collectQuestionText(question))) {
    issues.push('文本空格异常');
  }
  return issues;
}
