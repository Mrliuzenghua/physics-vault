import type { Question } from '../types';
import { normalizeProjectImagePath } from '../utils/imageUrl';

function safeJsonParse<T>(value: unknown, fallback: T): T {
  if (value == null || value === '') {
    return fallback;
  }
  if (typeof value !== 'string') {
    return value as T;
  }
  try {
    return JSON.parse(value) as T;
  } catch {
    return fallback;
  }
}

export function normalizeQuestion(raw: Question | Record<string, unknown>): Question {
  const source = raw as Record<string, unknown>;
  const titleText = String(source.title ?? source.title_text ?? '').trim();
  const stemText = titleText || String(source.stem_text ?? source.canonical_title ?? '').trim();
  const answerText = String(source.answer ?? source.answer_text ?? '').trim();
  const analysisText = String(source.analysis ?? source.analysis_text ?? '').trim();
  const sourceText = String(source.source ?? source.source_text ?? '').trim()
    || String(source.primary_paper_id ?? source.source_id ?? '').trim();
  const questionType = String(source.question_type ?? source.type ?? '').trim() as Question['question_type'];
  const difficultyValue = source.difficulty;
  const difficulty =
    typeof difficultyValue === 'number'
      ? difficultyValue
      : Number.parseInt(String(difficultyValue ?? 0), 10) || 0;

  return {
    question_id: String(source.question_id ?? ''),
    question_type: questionType,
    title: stemText,
    options: normalizeOptions(source.options ?? source.options_json),
    answer: answerText,
    analysis: analysisText,
    sub_questions: safeJsonParse(source.sub_questions ?? source.sub_questions_json, [] as Question['sub_questions']),
    figures: normalizeFigures(source),
    difficulty,
    knowledge_point: String(source.knowledge_point ?? source.topic3 ?? ''),
    knowledge_points: safeJsonParse(source.knowledge_points, [] as Question['knowledge_points']),
    tags: safeJsonParse(source.tags ?? source.tags_json, [] as Question['tags']),
    source: sourceText,
    year: source.year != null ? Number(source.year) : undefined,
    import_batch_id: source.import_batch_id ? String(source.import_batch_id) : undefined,
    origin_file: source.origin_file ? String(source.origin_file) : undefined,
    origin_page: source.origin_page != null ? Number(source.origin_page) : undefined,
    review_status: String(source.review_status ?? '').trim() as Question['review_status'],
    review_comment: source.review_comment ? String(source.review_comment) : undefined,
    is_mistake: Boolean(source.is_mistake),
    mistake_marked_at: source.mistake_marked_at ? String(source.mistake_marked_at) : null,
    annotation_count: source.annotation_count != null ? Number(source.annotation_count) : undefined,
    status: source.status ? String(source.status) : undefined,
    module: source.module ? String(source.module) : undefined,
    topic2: source.topic2 ? String(source.topic2) : undefined,
    topic3: source.topic3 ? String(source.topic3) : undefined,
    primary_paper_id: source.primary_paper_id ? String(source.primary_paper_id) : undefined,
    primary_question_no: source.primary_question_no != null ? String(source.primary_question_no) : undefined,
    canonical_title: source.canonical_title ? String(source.canonical_title) : undefined,
    has_media: Boolean(source.has_media),
    stem_text: source.stem_text ? String(source.stem_text) : stemText,
    model_type: source.model_type ? String(source.model_type) : undefined,
    experiment_type: source.experiment_type ? String(source.experiment_type) : undefined,
    created_at: source.created_at ? String(source.created_at) : undefined,
    updated_at: source.updated_at ? String(source.updated_at) : undefined,
    keyword_match: source.keyword_match != null ? Boolean(source.keyword_match) : undefined,
    similarity: source.similarity != null ? Number(source.similarity) : undefined,
    score: source.score != null ? Number(source.score) : undefined,
  };
}

function normalizeOptions(raw: unknown): Question['options'] {
  const parsed = safeJsonParse(raw, [] as Array<Record<string, unknown>>);
  if (!Array.isArray(parsed)) return [];
  return parsed.map((item, index) => {
    const option = item as Record<string, unknown>;
    const opt = String(option.opt ?? option.label ?? String.fromCharCode(65 + index)).trim();
    const content = String(option.content ?? option.text ?? '').trim();
    return { opt, content };
  });
}

function normalizeFigures(source: Record<string, unknown>): Question['figures'] {
  const directFigures = safeJsonParse(source.figures, [] as unknown[]);
  const figureList = directFigures.length > 0
    ? directFigures
    : safeJsonParse(source.figures_json, [] as unknown[]);
  const idList = safeJsonParse(source.image_asset_ids ?? source.image_asset_ids_json, [] as string[]);

  if (figureList.length > 0 && figureList.every((item) => typeof item === 'object' && item !== null)) {
    return figureList.map((item, index) => {
      const figure = item as Record<string, unknown>;
      const localPath = normalizeProjectImagePath(
        String(figure.local_path ?? figure.file_path ?? figure.path ?? ''),
      ) || '';
      return {
        fig_uuid: String(figure.fig_uuid ?? figure.asset_id ?? idList[index] ?? `img-${index}`),
        local_path: localPath,
      };
    });
  }

  const directNames = safeJsonParse(source.image_filenames, [] as unknown[]);
  const nameList = directNames.length > 0
    ? directNames
    : safeJsonParse(source.image_filenames_json, [] as unknown[]);

  return (nameList as string[]).map((filename: string, index: number) => ({
    fig_uuid: idList[index] || `img-${index}`,
    local_path: normalizeProjectImagePath(filename) || '',
  }));
}
