import type { LessonPackage, PaperDraft, PaperDraftItem, PaperDraftListResponse } from '../types';
import { ApiError, request } from './apiClient.ts';

export async function listPaperDrafts(limit = 30): Promise<PaperDraftListResponse> {
  return request(`/api/paper-drafts?limit=${limit}`);
}

export async function fetchLatestPaperDraft(): Promise<PaperDraft | null> {
  return request('/api/paper-drafts/latest');
}

export async function fetchPaperDraft(draftId: string): Promise<PaperDraft | null> {
  try {
    return await request(`/api/paper-drafts/${encodeURIComponent(draftId)}`);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null;
    throw error;
  }
}

export async function savePaperDraft(
  pkg: LessonPackage,
  qualityReport: Record<string, unknown> = {},
  documentRevision = 0,
  baseUpdatedAt: string | null = null,
): Promise<PaperDraft> {
  const questionMap = new Map(pkg.questions.map((question) => [question.question_id, question]));
  const textMap = new Map(pkg.textBlocks.map((block) => [block.id, block]));
  const knowledgeMap = new Map(pkg.knowledgeCards.map((card) => [card.id, card]));
  const items: PaperDraftItem[] = pkg.nodes.map((node, position) => {
    if (node.type === 'question') {
      const question = questionMap.get(node.questionId);
      return {
        id: node.id, type: 'question', position, question_id: node.questionId,
        title: question?.title || question?.canonical_title || node.questionId,
        score: estimateQuestionScore(question?.question_type),
        payload: {
          question_type: question?.question_type, difficulty: question?.difficulty,
          source: question?.source || question?.origin_file || question?.primary_paper_id,
          question_snapshot: question ? { ...question } : undefined,
        },
      };
    }
    if (node.type === 'text') {
      const block = textMap.get(node.textBlockId);
      return { id: node.id, type: 'text', position, title: block?.title || '文本', payload: block ? { ...block } : {} };
    }
    if (node.type === 'knowledge') {
      const card = knowledgeMap.get(node.knowledgeId);
      return { id: node.id, type: 'knowledge', position, title: card?.title || '知识点', payload: card ? { ...card } : {} };
    }
    return { id: node.id, type: 'page_break', position, title: node.title || '分页', payload: { title: node.title } };
  });

  return request('/api/paper-drafts', {
    method: 'POST',
    body: JSON.stringify({
      id: pkg.id, base_updated_at: baseUpdatedAt, title: pkg.title, subtitle: pkg.subtitle, source: pkg.source, status: 'draft', items,
      metadata: { documentRevision, headerFooter: pkg.headerFooter, styleConfig: pkg.styleConfig, formatSpec: pkg.formatSpec, slideTemplate: pkg.slideTemplate },
      quality_report: qualityReport,
    }),
  });
}

function estimateQuestionScore(questionType?: string): number {
  if (questionType === 'calculation') return 12;
  if (questionType === 'experiment') return 10;
  if (questionType === 'multi_choice') return 6;
  return 5;
}
