import type { Question } from '../types';

export function getQuestionSourceLabel(
  question?: Pick<Question, 'source' | 'origin_file' | 'primary_paper_id'> | null,
  fallback = '',
): string {
  if (!question) return fallback;
  return [question.source, question.origin_file, question.primary_paper_id]
    .map((value) => String(value || '').trim())
    .find(Boolean) || fallback;
}
