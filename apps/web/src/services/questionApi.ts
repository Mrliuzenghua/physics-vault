import type {
  FilterFacets,
  KnowledgePoint,
  KnowledgePointFlatItem,
  Question,
  QuestionVersionDetail,
  QuestionVersionSummary,
  SearchFilters,
  SearchResponse,
  SimilarQuestionItem,
  SimilarQuestionsResponse,
} from '../types';
import { request } from './apiClient.ts';
import { normalizeQuestion } from './questionNormalizer.ts';

export interface DeleteQuestionsResponse {
  requested_count: number;
  deleted_count: number;
  missing_ids: string[];
}

export interface ReturnQuestionToReviewResponse {
  question_id: string;
  review_id?: string | null;
  status: 'queued';
  message: string;
}

export interface RollbackQuestionVersionResponse {
  ok: boolean;
  message: string;
}

export interface QuestionAsset {
  path: string;
  type: string;
}

function buildSearchParams(filters: SearchFilters): URLSearchParams {
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') {
      params.set(key, String(value));
    }
  });
  return params;
}

export async function searchQuestions(filters: SearchFilters): Promise<SearchResponse> {
  const params = buildSearchParams(filters);
  // BrowsePage does not render the full facet payload. Avoid regenerating and
  // transferring it for every page of results.
  params.set('include_facets', 'false');
  const result = await request<SearchResponse | Question[]>(`/api/search/questions?${params}`);
  if (Array.isArray(result)) {
    return {
      items: result.map(normalizeQuestion),
      total: result.length,
      limit: filters.limit ?? result.length,
      offset: filters.offset ?? 0,
      search_mode: filters.search_mode ?? 'browse',
      facets: undefined,
    } as SearchResponse;
  }
  if (Array.isArray(result.items)) {
    return { ...result, items: result.items.map(normalizeQuestion) };
  }
  return result;
}

export async function fetchFacets(): Promise<FilterFacets> {
  return request('/api/filters/facets');
}

export async function fetchQuestion(id: string): Promise<Question> {
  const result = await request<Question | Record<string, unknown>>(`/api/questions/${encodeURIComponent(id)}`);
  return normalizeQuestion(result);
}

export async function fetchQuestionsByIds(questionIds: string[]): Promise<Question[]> {
  if (questionIds.length === 0) return [];
  const result = await request<{ items: Array<Question | Record<string, unknown>>; missing_ids: string[] }>(
    '/api/questions/batch-get',
    { method: 'POST', body: JSON.stringify({ question_ids: questionIds }) },
  );
  return result.items.map(normalizeQuestion);
}

export async function deleteQuestions(questionIds: string[]): Promise<DeleteQuestionsResponse> {
  return request('/api/questions/batch-delete', {
    method: 'POST',
    body: JSON.stringify({ question_ids: questionIds }),
  });
}

export async function returnQuestionToReview(
  questionId: string,
  reason = '题目需要回炉重造',
): Promise<ReturnQuestionToReviewResponse> {
  return request(`/api/questions/${encodeURIComponent(questionId)}/return-to-review`, {
    method: 'POST',
    body: JSON.stringify({ reason, reviewer: 'teacher' }),
  });
}

export async function updateQuestion(id: string, data: Partial<Question>): Promise<Question> {
  // Image bindings are managed by dedicated endpoints, not by the question PUT.
  const contentData = { ...data };
  delete contentData.figures;
  delete contentData.image_filenames;
  delete contentData.image_asset_ids;
  delete contentData.image_count;
  delete contentData.has_media;
  delete contentData.stem_text;
  delete contentData.canonical_title;

  const result = await request<Question | Record<string, unknown>>(`/api/questions/${encodeURIComponent(id)}`, {
    method: 'PUT',
    body: JSON.stringify(contentData),
  });
  const normalized = normalizeQuestion(result);
  return {
    ...normalized,
    figures: data.figures ?? normalized.figures ?? [],
    image_filenames: normalized.image_filenames?.length ? normalized.image_filenames : data.image_filenames,
    image_asset_ids: normalized.image_asset_ids?.length ? normalized.image_asset_ids : data.image_asset_ids,
    image_count: normalized.image_count || data.image_count || 0,
    has_media: normalized.has_media ?? data.has_media,
  };
}

export async function fetchQuestionVersions(questionId: string): Promise<QuestionVersionSummary[]> {
  return request(`/api/questions/${encodeURIComponent(questionId)}/versions`);
}

export async function fetchQuestionVersionDetail(
  questionId: string,
  versionId: string,
): Promise<QuestionVersionDetail> {
  return request(`/api/questions/${encodeURIComponent(questionId)}/versions/${encodeURIComponent(versionId)}`);
}

export async function rollbackQuestionVersion(
  questionId: string,
  versionId: string,
): Promise<RollbackQuestionVersionResponse> {
  return request(
    `/api/questions/${encodeURIComponent(questionId)}/versions/${encodeURIComponent(versionId)}/rollback`,
    { method: 'POST', body: JSON.stringify({ modified_by: 'teacher' }) },
  );
}

export async function fetchQuestionKnowledgePoints(id: string): Promise<KnowledgePoint[]> {
  return request(`/api/questions/${encodeURIComponent(id)}/knowledge-points`);
}

export async function updateQuestionKnowledgePoints(id: string, points: KnowledgePoint[]): Promise<void> {
  await request(`/api/questions/${encodeURIComponent(id)}/knowledge-points`, {
    method: 'PUT',
    body: JSON.stringify(points),
  });
}

export async function fetchKnowledgePoints(): Promise<KnowledgePointFlatItem[]> {
  return request('/api/knowledge-points');
}

export async function fetchKnowledgePointCounts(): Promise<Record<string, number>> {
  return request('/api/knowledge-points/counts');
}

export async function fetchQuestionAssets(id: string): Promise<QuestionAsset[]> {
  return request(`/api/questions/${encodeURIComponent(id)}/assets`);
}

export async function fetchSimilarQuestions(
  questionId: string,
  limit = 10,
): Promise<SimilarQuestionsResponse> {
  const params = new URLSearchParams({ limit: String(limit) });
  try {
    const raw = await request<Record<string, unknown>>(
      `/api/questions/${encodeURIComponent(questionId)}/similar?${params}`,
    );
    const items = (Array.isArray(raw.items) ? raw.items : []).map(
      (item: Record<string, unknown>) => ({
        ...item,
        similarity_score:
          (item.similarity_score as number) ??
          (item.similarity as number) ??
          (item.similarityScore as number) ??
          0,
        title: (item.title as string) || (item.question_id as string) || '',
        question_type: item.question_type || null,
        difficulty: item.difficulty || null,
      }),
    );
    return {
      question_id: (raw.question_id as string) || questionId,
      items: items as SimilarQuestionItem[],
      total_candidates: (raw.total_candidates as number) || 0,
      limit: (raw.limit as number) || limit,
    };
  } catch (error) {
    if (error instanceof Error && /Not Found|HTTP 404/i.test(error.message)) {
      return { question_id: questionId, items: [], total_candidates: 0, limit };
    }
    throw error;
  }
}
