import { collectQuestionFigureReferences } from '../../services/questionQuality.ts';
import type {
  Figure,
  FigureReferenceIssue,
  KnowledgeReviewDraft,
  Option,
  ReviewQuestionDraft,
  SubQuestion,
} from '../../types';
import { normalizeShortInlineDisplayMath } from '../mathText.ts';

const REVIEW_FIELD_LABELS: Partial<Record<keyof ReviewQuestionDraft, string>> = {
  question_type: '题型',
  title: '题干',
  options: '选项',
  answer: '答案',
  analysis: '解析',
  difficulty: '难度',
  knowledge_point: '知识点',
  tags: '标签',
  source: '来源',
  figures: '配图',
};

const REVIEW_DIFF_FIELDS = Object.keys(REVIEW_FIELD_LABELS) as (keyof ReviewQuestionDraft)[];
const REVIEW_STATUSES: ReviewQuestionDraft['status'][] = ['pending', 'modified', 'confirmed', 'discarded'];

function isReviewStatus(value: string): value is ReviewQuestionDraft['status'] {
  return REVIEW_STATUSES.includes(value as ReviewQuestionDraft['status']);
}

function isClearlyExperimentQuestion(content: string): boolean {
  const text = content.replace(/!\[fig:[^\]]+\]/g, ' ');
  const hasStrongPhrase = /(在.{0,24}(?:实验|探究)中|实验(?:步骤|装置|器材|数据|原理)|测绘.{0,20}特性曲线|连接.{0,16}电路|完成.{0,16}实验)/.test(text);
  const stepCount = (text.match(/[①②③④⑤⑥⑦⑧⑨⑩]|(?:^|\n)\s*[（(]\d+[)）]/g) ?? []).length;
  return hasStrongPhrase && (stepCount >= 2 || /实验(?:中|步骤|装置|器材|数据|原理)/.test(text));
}

export function normalizeOptions(options: unknown): Option[] {
  if (!Array.isArray(options)) return [];
  return options
    .filter((item): item is Record<string, unknown> => typeof item === 'object' && item !== null)
    .map((item) => ({
      opt: String(item.opt ?? ''),
      content: normalizeShortInlineDisplayMath(String(item.content ?? '')),
    }));
}

export function normalizeSourceBBox(value: unknown): [number, number, number, number] | null {
  if (!Array.isArray(value) || value.length !== 4) return null;
  const numbers = value.map(Number);
  if (numbers.some((item) => !Number.isFinite(item))) return null;
  return numbers as [number, number, number, number];
}

export function computeFigureIssues(question: Pick<ReviewQuestionDraft, 'title' | 'options' | 'answer' | 'analysis' | 'figures'>): FigureReferenceIssue[] {
  const issues: FigureReferenceIssue[] = [];
  const referenced = collectQuestionFigureReferences(question);
  const actual = new Set(question.figures.map((figure) => figure.fig_uuid));
  for (const figure of question.figures) {
    if (!referenced.has(figure.fig_uuid)) issues.push({ type: 'unreferenced_figure', message: `图片 ${figure.fig_uuid} 未被题目内容引用`, figUuid: figure.fig_uuid });
  }
  for (const uuid of referenced) {
    if (!actual.has(uuid)) issues.push({ type: 'missing_figure', message: `题干引用了不存在的图片 ${uuid}`, figUuid: uuid });
  }
  return issues;
}

export function normalizeDraft(raw: Record<string, unknown>, index: number): ReviewQuestionDraft {
  const title = normalizeShortInlineDisplayMath(String(raw.title ?? raw.stem ?? ''));
  const figures = Array.isArray(raw.figures) ? (raw.figures as Figure[]) : [];
  const options = normalizeOptions(raw.options);
  const answer = normalizeShortInlineDisplayMath(String(raw.answer ?? ''));
  const analysis = normalizeShortInlineDisplayMath(String(raw.analysis ?? ''));
  const suppliedQuestionType = String(raw.question_type || 'calculation');
  const experimentText = [title, ...options.map((option) => option.content)].join('\n');
  const questionType = ['single_choice', 'multi_choice'].includes(suppliedQuestionType) && isClearlyExperimentQuestion(experimentText)
    ? 'experiment'
    : suppliedQuestionType;
  const rawStatus = String(raw.status ?? raw.review_status ?? 'pending');
  const status = isReviewStatus(rawStatus) ? rawStatus : 'pending';
  return {
    question_id: String(raw.question_id ?? `draft-${index + 1}`),
    question_type: questionType,
    title,
    options,
    answer,
    analysis,
    sub_questions: Array.isArray(raw.sub_questions) ? (raw.sub_questions as SubQuestion[]) : [],
    figures,
    difficulty: raw.difficulty !== null && raw.difficulty !== undefined ? Number(raw.difficulty) : null,
    knowledge_point: String(raw.knowledge_point ?? ''),
    knowledge_points: Array.isArray(raw.knowledge_points) ? raw.knowledge_points as ReviewQuestionDraft['knowledge_points'] : [],
    topic3_ids: Array.isArray(raw.topic3_ids) ? raw.topic3_ids.map(String) : [],
    topic1_id: String(raw.topic1_id ?? ''),
    topic1_name: String(raw.topic1_name ?? ''),
    topic2_id: String(raw.topic2_id ?? ''),
    topic2_name: String(raw.topic2_name ?? ''),
    topic3_id: String(raw.topic3_id ?? ''),
    topic3_name: String(raw.topic3_name ?? ''),
    tags: Array.isArray(raw.tags) ? raw.tags.map(String) : [],
    source: String(raw.source ?? ''),
    year: raw.year !== null && raw.year !== undefined ? Number(raw.year) : null,
    import_batch_id: raw.import_batch_id ? String(raw.import_batch_id) : undefined,
    source_page: raw.source_page !== null && raw.source_page !== undefined ? Number(raw.source_page) : null,
    source_region_id: raw.source_region_id ? String(raw.source_region_id) : null,
    source_bbox: normalizeSourceBBox(raw.source_bbox),
    raw_text: raw.raw_text ? normalizeShortInlineDisplayMath(String(raw.raw_text)) : null,
    status,
    figureIssues: computeFigureIssues({ title, options, answer, analysis, figures }),
  };
}

export function normalizeKnowledgeDraft(raw: Record<string, unknown>, index: number): KnowledgeReviewDraft {
  const draftId = String(raw.draft_id ?? raw.topic3_id ?? `knowledge-draft-${index + 1}`);
  const rawStatus = String(raw.status);
  return {
    draft_id: draftId,
    topic3_id: String(raw.topic3_id ?? draftId),
    topic3_name: String(raw.topic3_name ?? raw.title ?? raw.name ?? ''),
    topic2_id: String(raw.topic2_id ?? ''),
    topic2_name: String(raw.topic2_name ?? raw.module ?? ''),
    topic1_id: String(raw.topic1_id ?? ''),
    topic1_name: String(raw.topic1_name ?? ''),
    source_chapter: String(raw.source_chapter ?? ''),
    definition: normalizeShortInlineDisplayMath(String(raw.definition ?? raw.content ?? '')),
    formula: normalizeShortInlineDisplayMath(String(raw.formula ?? '')),
    key_summary: normalizeShortInlineDisplayMath(String(raw.key_summary ?? raw.summary ?? '')),
    error_prone: normalizeShortInlineDisplayMath(String(raw.error_prone ?? raw.common_mistakes ?? '')),
    example_analysis: normalizeShortInlineDisplayMath(String(raw.example_analysis ?? raw.example ?? '')),
    tags: Array.isArray(raw.tags) ? raw.tags.map(String) : [],
    raw_text: String(raw.raw_text ?? ''),
    status: isReviewStatus(rawStatus) ? rawStatus : 'pending',
  };
}

export function cloneDraft(draft: ReviewQuestionDraft): ReviewQuestionDraft {
  return JSON.parse(JSON.stringify(draft)) as ReviewQuestionDraft;
}

export function getChangedReviewFields(original: ReviewQuestionDraft | null, draft: ReviewQuestionDraft | null): (keyof ReviewQuestionDraft)[] {
  if (!original || !draft) return [];
  return REVIEW_DIFF_FIELDS.filter((field) => JSON.stringify(original[field] ?? null) !== JSON.stringify(draft[field] ?? null));
}

export function displayReviewValue(value: unknown): string {
  if (Array.isArray(value)) {
    if (value.length === 0) return '（空）';
    if (value.every((item) => typeof item === 'string')) return value.join('、');
    if (value.every((item) => typeof item === 'object' && item !== null && 'content' in item)) {
      return value.map((item) => `${String((item as Option).opt || '')}. ${String((item as Option).content || '')}`).join('\n');
    }
    return value.map((item) => typeof item === 'object' && item !== null && 'fig_uuid' in item ? String((item as Figure).fig_uuid) : String(item)).join('、');
  }
  const text = String(value ?? '').trim();
  return text || '（空）';
}

export function applyAiPatch(text: string): Partial<ReviewQuestionDraft> {
  const trimmed = text.trim();
  try {
    if (trimmed.startsWith('{')) {
      const data = JSON.parse(trimmed) as Record<string, unknown>;
      return {
        ...(typeof data.question_type === 'string' ? { question_type: data.question_type } : {}),
        ...(typeof data.difficulty === 'number' ? { difficulty: Math.max(1, Math.min(5, data.difficulty)) } : {}),
        ...(typeof data.knowledge_point === 'string' ? { knowledge_point: data.knowledge_point } : {}),
        ...(Array.isArray(data.tags) ? { tags: data.tags.map(String) } : {}),
        ...(typeof data.source === 'string' ? { source: data.source } : {}),
        ...(typeof data.answer === 'string' ? { answer: normalizeShortInlineDisplayMath(data.answer) } : {}),
        ...(Array.isArray(data.options) ? { options: normalizeOptions(data.options) } : {}),
        ...(typeof data.analysis === 'string' ? { analysis: normalizeShortInlineDisplayMath(data.analysis) } : {}),
        ...(Array.isArray(data.sub_questions) ? { sub_questions: data.sub_questions as SubQuestion[] } : {}),
      };
    }
  } catch {
    // Keep the generated text as analysis if it is not valid JSON.
  }
  return { analysis: normalizeShortInlineDisplayMath(text) };
}
