import type { Figure, Option } from '../types';

export type QuestionQualitySeverity = 'danger' | 'warning' | 'suggestion';
export type QuestionQualityCode =
  | 'empty_title'
  | 'missing_answer'
  | 'missing_options'
  | 'too_few_options'
  | 'duplicate_options'
  | 'answer_option_mismatch'
  | 'missing_knowledge'
  | 'missing_source'
  | 'image_issue'
  | 'duplicate_question'
  | 'latex_delimiter'
  | 'ocr_artifact';

export interface QualityQuestion {
  question_type: string;
  title: string;
  options: Option[];
  answer: string;
  analysis?: string;
  figures: Figure[];
  knowledge_point?: string;
  source?: string;
}

export interface QuestionQualityIssue {
  code: QuestionQualityCode;
  severity: QuestionQualitySeverity;
  field: 'title' | 'options' | 'answer' | 'analysis' | 'knowledge_point' | 'source' | 'figures';
  message: string;
}

export interface QuestionQualityRuleConfig {
  enabled?: Partial<Record<QuestionQualityCode, boolean>>;
  severity?: Partial<Record<QuestionQualityCode, QuestionQualitySeverity>>;
  penalties?: Partial<Record<QuestionQualitySeverity, number>>;
  minimumChoiceOptions?: number;
}

export interface QuestionQualityContext {
  questionId?: string;
  duplicateIds?: ReadonlySet<string>;
  requireKnowledge?: boolean;
  requireSource?: boolean;
  config?: QuestionQualityRuleConfig;
}

export interface QuestionQualitySummary {
  score: number;
  issueQuestionCount: number;
  danger: number;
  warning: number;
  suggestion: number;
  totalIssues: number;
}

export const DEFAULT_QUESTION_QUALITY_CONFIG: {
  penalties: Record<QuestionQualitySeverity, number>;
  minimumChoiceOptions: number;
} = {
  penalties: { danger: 14, warning: 6, suggestion: 2 },
  minimumChoiceOptions: 2,
};

export const QUESTION_QUALITY_RULE_LABELS: Record<QuestionQualityCode, string> = {
  empty_title: '题干为空',
  missing_answer: '缺少答案',
  missing_options: '选择题缺少选项',
  too_few_options: '选择题选项过少',
  duplicate_options: '选项内容重复',
  answer_option_mismatch: '答案与选项不匹配',
  missing_knowledge: '缺少知识点',
  missing_source: '缺少来源',
  image_issue: '图片引用异常',
  duplicate_question: '疑似重复题',
  latex_delimiter: 'LaTeX 分隔符异常',
  ocr_artifact: '疑似 OCR 乱码',
};

const FIGURE_REFERENCE_PATTERN = /!\[fig:([^\]]+)\]/g;

function normalizedComparableText(value: string): string {
  return value
    .replace(FIGURE_REFERENCE_PATTERN, '')
    .replace(/\$+[^$]*\$+/g, '')
    .replace(/[\s\p{P}\p{S}]+/gu, '')
    .toLowerCase();
}

export function questionFingerprint(question: QualityQuestion): string {
  return normalizedComparableText(question.title).slice(0, 220);
}

export function findDuplicateQuestionIds<T extends QualityQuestion>(questions: T[], getId: (question: T) => string): Set<string> {
  const groups = new Map<string, string[]>();
  for (const question of questions) {
    const fingerprint = questionFingerprint(question);
    if (fingerprint.length < 18) continue;
    const ids = groups.get(fingerprint) ?? [];
    ids.push(getId(question));
    groups.set(fingerprint, ids);
  }
  return new Set([...groups.values()].filter((ids) => ids.length > 1).flat());
}

function hasUnbalancedLatex(value: string): boolean {
  const delimiters = value.replace(/\\\$/g, '').match(/\$/g)?.length ?? 0;
  return delimiters % 2 !== 0;
}

function hasOcrArtifact(value: string): boolean {
  return /锟|�|[\uE000-\uF8FF]/u.test(value);
}

function normalizedOptionContent(value: string): string {
  return value.replace(/[\s\p{P}\p{S}]+/gu, '').toLowerCase();
}

export function analyzeQuestionQuality(question: QualityQuestion, context: QuestionQualityContext = {}): QuestionQualityIssue[] {
  const issues: QuestionQualityIssue[] = [];
  const addIssue = (issue: QuestionQualityIssue) => {
    if (context.config?.enabled?.[issue.code] === false) return;
    issues.push({ ...issue, severity: context.config?.severity?.[issue.code] ?? issue.severity });
  };
  const isChoice = question.question_type === 'single_choice' || question.question_type === 'multi_choice';
  const title = question.title.trim();
  const answer = question.answer.trim();
  const minimumChoiceOptions = Math.max(1, context.config?.minimumChoiceOptions ?? DEFAULT_QUESTION_QUALITY_CONFIG.minimumChoiceOptions);

  if (!title) addIssue({ code: 'empty_title', severity: 'danger', field: 'title', message: '题干为空' });
  if (!answer) addIssue({ code: 'missing_answer', severity: 'warning', field: 'answer', message: '缺少答案' });
  if (isChoice && question.options.length === 0) {
    addIssue({ code: 'missing_options', severity: 'danger', field: 'options', message: '选择题缺少选项' });
  } else if (isChoice && question.options.length < minimumChoiceOptions) {
    addIssue({ code: 'too_few_options', severity: 'warning', field: 'options', message: `选择题选项少于 ${minimumChoiceOptions} 个` });
  }

  const optionContents = question.options.map((option) => normalizedOptionContent(option.content)).filter(Boolean);
  if (new Set(optionContents).size < optionContents.length) {
    addIssue({ code: 'duplicate_options', severity: 'warning', field: 'options', message: '存在内容重复的选项' });
  }

  if (isChoice && answer) {
    const available = new Set(question.options.map((option) => option.opt.trim().toUpperCase()).filter(Boolean));
    const selected = [...new Set(answer.toUpperCase().match(/[A-H]/g) ?? [])];
    if (selected.length > 0 && selected.some((label) => !available.has(label))) {
      addIssue({ code: 'answer_option_mismatch', severity: 'danger', field: 'answer', message: '答案引用了不存在的选项' });
    }
  }

  if (context.requireKnowledge && !question.knowledge_point?.trim()) {
    addIssue({ code: 'missing_knowledge', severity: 'warning', field: 'knowledge_point', message: '未标知识点' });
  }
  if (context.requireSource && !question.source?.trim()) {
    addIssue({ code: 'missing_source', severity: 'suggestion', field: 'source', message: '缺少来源' });
  }

  const referenced = new Set(Array.from(title.matchAll(FIGURE_REFERENCE_PATTERN), (match) => match[1]));
  const actual = new Set(question.figures.map((figure) => figure.fig_uuid));
  if (question.figures.some((figure) => !referenced.has(figure.fig_uuid)) || [...referenced].some((uuid) => !actual.has(uuid))) {
    addIssue({ code: 'image_issue', severity: 'danger', field: 'figures', message: '图片引用与配图不一致' });
  }

  if (context.questionId && context.duplicateIds?.has(context.questionId)) {
    addIssue({ code: 'duplicate_question', severity: 'warning', field: 'title', message: '疑似重复题' });
  }

  const richTextFields: Array<['title' | 'answer' | 'analysis', string]> = [
    ['title', question.title],
    ['answer', question.answer],
    ['analysis', question.analysis ?? ''],
  ];
  for (const [field, value] of richTextFields) {
    const label = field === 'title' ? '题干' : field === 'answer' ? '答案' : '解析';
    if (value && hasUnbalancedLatex(value)) {
      addIssue({ code: 'latex_delimiter', severity: 'warning', field, message: `${label}中的 LaTeX 分隔符未闭合` });
    }
    if (value && hasOcrArtifact(value)) {
      addIssue({ code: 'ocr_artifact', severity: 'warning', field, message: `${label}含异常 OCR 字符` });
    }
  }

  return issues;
}

export function scoreQuestionQuality(issues: QuestionQualityIssue[], config: QuestionQualityRuleConfig = {}): number {
  const penalties: Record<QuestionQualitySeverity, number> = {
    danger: config.penalties?.danger ?? DEFAULT_QUESTION_QUALITY_CONFIG.penalties.danger,
    warning: config.penalties?.warning ?? DEFAULT_QUESTION_QUALITY_CONFIG.penalties.warning,
    suggestion: config.penalties?.suggestion ?? DEFAULT_QUESTION_QUALITY_CONFIG.penalties.suggestion,
  };
  const penalty = issues.reduce((total, issue) => total + penalties[issue.severity], 0);
  return Math.max(0, 100 - penalty);
}

export function summarizeQuestionQuality<T extends QualityQuestion>(questions: T[], getId: (question: T) => string, context: Omit<QuestionQualityContext, 'questionId' | 'duplicateIds'> = {}): QuestionQualitySummary {
  const duplicateIds = findDuplicateQuestionIds(questions, getId);
  const issueGroups = questions.map((question) => analyzeQuestionQuality(question, { ...context, questionId: getId(question), duplicateIds }));
  const allIssues = issueGroups.flat();
  const danger = allIssues.filter((issue) => issue.severity === 'danger').length;
  const warning = allIssues.filter((issue) => issue.severity === 'warning').length;
  const suggestion = allIssues.filter((issue) => issue.severity === 'suggestion').length;
  const averageScore = questions.length ? issueGroups.reduce((total, issues) => total + scoreQuestionQuality(issues, context.config), 0) / questions.length : 100;
  return {
    score: Math.round(averageScore),
    issueQuestionCount: issueGroups.filter((issues) => issues.length > 0).length,
    danger,
    warning,
    suggestion,
    totalIssues: allIssues.length,
  };
}

function cleanRichText(value: string): string {
  return value
    .replace(/\r\n?/g, '\n')
    .split('\n')
    .map((line) => line.replace(/[ \t]+$/g, ''))
    .join('\n')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}

export function buildSafeQuestionPatch(question: QualityQuestion): Pick<QualityQuestion, 'title' | 'options' | 'answer' | 'analysis'> {
  return {
    title: cleanRichText(question.title),
    options: question.options.map((option, index) => ({
      ...option,
      opt: String.fromCharCode(65 + index),
      content: cleanRichText(option.content),
    })),
    answer: cleanRichText(question.answer),
    analysis: cleanRichText(question.analysis ?? ''),
  };
}
