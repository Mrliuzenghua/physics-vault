import type {
  AiBatchTask,
  AiChatMessage,
  AiChatTestResponse,
  AiAssistantResponse,
  BasketItem,
  CleanDocumentRequest,
  CleanDocumentResponse,
  Collection,
  ConvertDocumentRequest,
  ConvertDocumentResponse,
  FilterFacets,
  ImportBatch,
  ImportBatchResponse,
  ImportPipelineTaskResponse,
  KnowledgePoint,
  KnowledgePointFlatItem,
  Layout,
  LessonPackage,
  McpConfig,
  AiCleanBatchResponse,
  AiStructureBatchResponse,
  AiRefineBatchResponse,
  PaperDraft,
  PaperDraftItem,
  PaperDraftListResponse,
  ExtractBatchImagesResponse,
  PandocBatchResponse,
  ParseStructuredQuestionsRequest,
  ParseStructuredQuestionsResponse,
  Question,
  RecognizeBatchResponse,
  RestorePackageResponse,
  SearchFilters,
  SearchResponse,
  SystemSettings,
  TaskLog,
  Template,
  UploadImportFileResponse,
} from '../types';
import { extractErrorMessage } from '../utils/error';
import { API_BASE as BASE, request } from './apiClient';
import { normalizeQuestion } from './questionNormalizer';

export {
  DEFAULT_AI_CONFIG,
  addToBasket,
  clearBasket,
  getBasket,
  getMcpConfig,
  getSettings,
  getTheme,
  pushMcpConfigToBackend,
  removeFromBasket,
  saveMcpConfig,
  saveSettings,
  saveTheme,
  subscribeBasket,
} from './clientState';
export {
  clearPersistedImportTasks,
  deleteMaterialPackage,
  deleteTemplate,
  loadMaterialPackages,
  loadPersistedImportTasks,
  loadTemplates,
  saveMaterialPackage,
  savePersistedImportTasks,
  saveTemplate,
} from './localPersistence';

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
  const result = await request<SearchResponse | Question[]>(`/search/questions?${buildSearchParams(filters)}`);
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
    return {
      ...result,
      items: result.items.map(normalizeQuestion),
    };
  }
  return result;
}

export async function fetchFacets(): Promise<FilterFacets> {
  return request('/filters/facets');
}

export async function fetchQuestion(id: string): Promise<Question> {
  const result = await request<Question | Record<string, unknown>>(`/questions/${id}`);
  return normalizeQuestion(result);
}

export async function fetchQuestionsByIds(questionIds: string[]): Promise<Question[]> {
  if (questionIds.length === 0) return [];
  const result = await request<{ items: Array<Question | Record<string, unknown>>; missing_ids: string[] }>(
    '/api/questions/batch-get',
    {
      method: 'POST',
      body: JSON.stringify({ question_ids: questionIds }),
    },
  );
  return result.items.map(normalizeQuestion);
}

export async function listPaperDrafts(limit = 30): Promise<PaperDraftListResponse> {
  return request(`/api/paper-drafts?limit=${limit}`);
}

export async function fetchLatestPaperDraft(): Promise<PaperDraft | null> {
  return request('/api/paper-drafts/latest');
}

export async function savePaperDraft(
  pkg: LessonPackage,
  qualityReport: Record<string, unknown> = {},
): Promise<PaperDraft> {
  const questionMap = new Map(pkg.questions.map((question) => [question.question_id, question]));
  const textMap = new Map(pkg.textBlocks.map((block) => [block.id, block]));
  const knowledgeMap = new Map(pkg.knowledgeCards.map((card) => [card.id, card]));
  const items: PaperDraftItem[] = pkg.nodes.map((node, position) => {
    if (node.type === 'question') {
      const question = questionMap.get(node.questionId);
      return {
        id: node.id,
        type: 'question',
        position,
        question_id: node.questionId,
        title: question?.title || question?.canonical_title || node.questionId,
        score: estimateQuestionScore(question?.question_type),
        payload: {
          question_type: question?.question_type,
          difficulty: question?.difficulty,
          source: question?.primary_paper_id || question?.source,
        },
      };
    }
    if (node.type === 'text') {
      const block = textMap.get(node.textBlockId);
      return {
        id: node.id,
        type: 'text',
        position,
        title: block?.title || '文本',
        payload: block ? { ...block } : {},
      };
    }
    if (node.type === 'knowledge') {
      const card = knowledgeMap.get(node.knowledgeId);
      return {
        id: node.id,
        type: 'knowledge',
        position,
        title: card?.title || '知识点',
        payload: card ? { ...card } : {},
      };
    }
    return {
      id: node.id,
      type: 'page_break',
      position,
      title: node.title || '分页',
      payload: { title: node.title },
    };
  });

  return request('/api/paper-drafts', {
    method: 'POST',
    body: JSON.stringify({
      id: pkg.id,
      title: pkg.title,
      subtitle: pkg.subtitle,
      source: pkg.source,
      status: 'draft',
      items,
      metadata: {
        headerFooter: pkg.headerFooter,
        styleConfig: pkg.styleConfig,
        slideTemplate: pkg.slideTemplate,
      },
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

export async function updateQuestion(id: string, data: Partial<Question>): Promise<Question> {
  // Strip image-related fields from the PUT payload. Images are managed
  // by the separate /api/questions/{id}/images API. Sending them back via
  // the question PUT would corrupt the filenames (local_path includes a
  // path prefix that gets stored as the filename).
  const contentData = { ...data };
  delete contentData.figures;
  delete contentData.image_filenames;
  delete contentData.image_asset_ids;
  delete contentData.image_count;
  delete contentData.has_media;
  delete contentData.stem_text;
  delete contentData.canonical_title;
  const result = await request<Question | Record<string, unknown>>(`/questions/${id}`, {
    method: 'PUT',
    body: JSON.stringify(contentData),
  });
  return normalizeQuestion(result);
}

// 鈹€鈹€ Question Version History 鈹€鈹€

export async function fetchQuestionVersions(
  questionId: string,
): Promise<import('../types').QuestionVersionSummary[]> {
  return request(`/questions/${encodeURIComponent(questionId)}/versions`);
}

export async function fetchQuestionVersionDetail(
  questionId: string,
  versionId: string,
): Promise<import('../types').QuestionVersionDetail> {
  return request(
    `/questions/${encodeURIComponent(questionId)}/versions/${encodeURIComponent(versionId)}`,
  );
}

export async function rollbackQuestionVersion(
  questionId: string,
  versionId: string,
): Promise<{ ok: boolean; message: string }> {
  return request(
    `/questions/${encodeURIComponent(questionId)}/versions/${encodeURIComponent(versionId)}/rollback`,
    { method: 'POST', body: JSON.stringify({ modified_by: 'teacher' }) },
  );
}

export async function fetchQuestionKnowledgePoints(id: string): Promise<KnowledgePoint[]> {
  return request(`/questions/${id}/knowledge-points`);
}

export async function updateQuestionKnowledgePoints(id: string, points: KnowledgePoint[]): Promise<void> {
  await request(`/questions/${id}/knowledge-points`, {
    method: 'PUT',
    body: JSON.stringify(points),
  });
}

export async function fetchKnowledgePoints(): Promise<KnowledgePointFlatItem[]> {
  return request('/knowledge-points');
}

export async function fetchKnowledgePointCounts(): Promise<Record<string, number>> {
  return request('/knowledge-points/counts');
}

export async function fetchQuestionAssets(id: string): Promise<{ path: string; type: string }[]> {
  return request(`/questions/${id}/assets`);
}

export async function fetchImages(params: Record<string, string>): Promise<unknown[]> {
  return request(`/images?${new URLSearchParams(params)}`);
}

export async function fetchPapers(): Promise<unknown[]> {
  return request('/papers');
}

export async function fetchPaperQuestions(paperId: string): Promise<Question[]> {
  return request(`/papers/${paperId}/questions`);
}

export async function fetchReviewQueue(): Promise<Question[]> {
  return request('/review-queue');
}

export async function fetchProcessingRuns(): Promise<TaskLog[]> {
  return request('/processing-runs');
}

export async function fetchEmbeddingStatus(): Promise<unknown> {
  return request('/embeddings/status');
}

export async function healthCheck(): Promise<{ status: string }> {
  return request('/health');
}

// 鈹€鈹€ MCP Runtime API 鈹€鈹€

export async function fetchMcpStatus(): Promise<import('../types').McpRuntimeStatus> {
  return request('/api/mcp/status');
}

export async function testMcpConnection(target: 'vl' | 'llm'): Promise<import('../types').McpConnectionTestResponse> {
  return request('/api/mcp/test-connection', {
    method: 'POST',
    body: JSON.stringify({ target }),
  });
}

export async function sendAiChatTest(
  messages: AiChatMessage[],
  temperature = 0.7,
): Promise<AiChatTestResponse> {
  return request('/api/mcp/chat-test', {
    method: 'POST',
    body: JSON.stringify({
      messages,
      temperature,
    }),
  });
}

// 鈹€鈹€ Import Pipeline API 鈹€鈹€

export async function uploadImportFile(file: File): Promise<UploadImportFileResponse> {
  const formData = new FormData();
  formData.append('file', file);

  const res = await fetch(`${BASE}/api/import/upload`, {
    method: 'POST',
    body: formData,
  });

  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(extractErrorMessage(error.detail || `HTTP ${res.status}`));
  }

  return res.json();
}

export async function createImportBatch(file: File): Promise<ImportBatchResponse> {
  const formData = new FormData();
  formData.append('file', file);

  const res = await fetch(`${BASE}/api/import/batches`, {
    method: 'POST',
    body: formData,
  });

  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(extractErrorMessage(error.detail || `HTTP ${res.status}`));
  }

  return res.json();
}

export async function runImportBatchPandoc(batchId: string): Promise<PandocBatchResponse> {
  return request(`/api/import/batches/${encodeURIComponent(batchId)}/pandoc`, {
    method: 'POST',
  });
}

export async function runImportBatchAiClean(batchId: string): Promise<AiCleanBatchResponse> {
  return request(`/api/import/batches/${encodeURIComponent(batchId)}/ai-clean`, {
    method: 'POST',
  });
}

export async function runImportBatchAiStructure(batchId: string): Promise<AiStructureBatchResponse> {
  return request(`/api/import/batches/${encodeURIComponent(batchId)}/ai-structure`, {
    method: 'POST',
  });
}

export async function runImportBatchRecognize(batchId: string): Promise<RecognizeBatchResponse> {
  return request(`/api/import/batches/${encodeURIComponent(batchId)}/recognize`, {
    method: 'POST',
  });
}

export async function extractBatchImages(batchId: string): Promise<ExtractBatchImagesResponse> {
  return request(`/api/import/batches/${encodeURIComponent(batchId)}/extract-images`, {
    method: 'POST',
  });
}

/** Second-pass AI proofreading on the current question list (review page). */
export async function runImportBatchAiRefine(
  batchId: string,
  questions: Record<string, unknown>[],
): Promise<AiRefineBatchResponse> {
  return request(`/api/import/batches/${encodeURIComponent(batchId)}/ai-refine`, {
    method: 'POST',
    body: JSON.stringify({ questions }),
  });
}

export async function sendAiAssistantChat(
  messages: AiChatMessage[],
  options?: { query?: string; contextLimit?: number; temperature?: number },
): Promise<AiAssistantResponse> {
  return request('/api/ai/assistant/chat', {
    method: 'POST',
    body: JSON.stringify({
      messages,
      query: options?.query,
      context_limit: options?.contextLimit ?? 8,
      temperature: options?.temperature ?? 0.35,
    }),
  });
}

export async function completeImportDraftMetadata(
  batchId: string,
  body: import('../types').DraftMetadataRequest,
): Promise<import('../types').DraftMetadataResponse> {
  return request(`/api/import/batches/${encodeURIComponent(batchId)}/draft-metadata`, {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

/** Confirm user-edited questions 鈫?returns task_id for the review workbench. */
export async function confirmImportBatch(
  batchId: string,
  questions: Record<string, unknown>[],
): Promise<{ task_id: string; batch_id: string; question_count: number }> {
  return request(`/api/import/batches/${encodeURIComponent(batchId)}/confirm`, {
    method: 'POST',
    body: JSON.stringify({ questions }),
  });
}

/** Upload an extra image into the batch media library. */
export async function uploadBatchImage(
  batchId: string,
  file: File,
): Promise<import('../types').ImportMediaAsset> {
  const formData = new FormData();
  formData.append('file', file);

  const res = await fetch(`${BASE}/api/import/batches/${encodeURIComponent(batchId)}/images`, {
    method: 'POST',
    body: formData,
  });

  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(extractErrorMessage(error.detail || `HTTP ${res.status}`));
  }
  return res.json();
}

export async function convertDocument(body: ConvertDocumentRequest): Promise<ConvertDocumentResponse> {
  return request('/api/import/convert', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export async function cleanDocument(body: CleanDocumentRequest): Promise<CleanDocumentResponse> {
  return request('/api/import/clean', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export async function parseStructuredQuestions(
  body: ParseStructuredQuestionsRequest,
): Promise<ParseStructuredQuestionsResponse> {
  return request('/api/import/parse', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export async function fetchImportTask(taskId: string): Promise<ImportPipelineTaskResponse> {
  return request(`/api/import/tasks/${taskId}`);
}

export async function importQuestion(body: {
  classification: Record<string, unknown>;
  source: Record<string, unknown>;
  content: Record<string, unknown>;
  images?: Array<Record<string, unknown>>;
  knowledge_points?: Array<Record<string, unknown>>;
  metadata?: Record<string, unknown>;
  reviewer?: string;
  note?: string;
}): Promise<{
  question_id: string;
  status: string;
  knowledge_points_inserted: number;
  images_linked: number;
  skipped_knowledge_points: string[];
  review_id: string;
}> {
  return request('/questions/import', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export async function aiParseDocument(
  body: import('../types').AiParseDocumentRequest,
): Promise<import('../types').AiParseDocumentResponse> {
  return request('/api/import/ai-parse-document', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

// 鈹€鈹€ Export Package 鈹€鈹€

/** Trigger a download of the export package zip file. */
export async function downloadExportPackage(): Promise<void> {
  const res = await fetch('/api/system/export-package');
  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: '瀵煎嚭澶辫触' }));
    const msg = typeof error.detail === 'object' ? error.detail?.message || JSON.stringify(error.detail) : error.detail || '瀵煎嚭澶辫触';
    throw new Error(msg);
  }
  const blob = await res.blob();
  const disposition = res.headers.get('Content-Disposition') || '';
  const match = disposition.match(/filename="?([^";\s]+)"?/);
  const filename = match?.[1] || 'physics-vault-export.zip';
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

// 鈹€鈹€ Review Save API 鈹€鈹€

export async function saveReviewedQuestions(
  body: import('../types').SaveReviewedQuestionsRequest,
): Promise<import('../types').SaveReviewedQuestionsResponse> {
  return request('/api/review/save', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

// 鈹€鈹€ Assets Manager API 鈹€鈹€

export async function fetchAssetList(
  filterMode: string = 'all',
  keyword: string = '',
): Promise<import('../types').AssetListResponse> {
  const params = new URLSearchParams({ filter_mode: filterMode, keyword });
  return request(`/api/assets?${params}`);
}

export async function cleanupUnreferencedAssets(): Promise<import('../types').CleanupResponse> {
  return request('/api/assets/cleanup-unreferenced', { method: 'POST' });
}

export async function deleteSingleAsset(filename: string): Promise<import('../types').DeleteAssetResponse> {
  return request(`/api/assets/${encodeURIComponent(filename)}`, { method: 'DELETE' });
}

// 鈹€鈹€ Image Management API 鈹€鈹€

export async function fetchQuestionImages(id: string): Promise<import('../types').ImageListResponse> {
  return request(`/api/questions/${encodeURIComponent(id)}/images`);
}

export async function addQuestionImage(id: string, body: {
  asset_id: string; role?: string; sort_order?: number; placeholder_key?: string; is_primary?: boolean;
}): Promise<import('../types').QuestionImageDetail> {
  return request(`/api/questions/${encodeURIComponent(id)}/images`, {
    method: 'POST', body: JSON.stringify(body),
  });
}

export async function replaceQuestionImage(id: string, assetId: string, body: {
  old_asset_id: string; new_asset_id: string;
}): Promise<import('../types').QuestionImageDetail> {
  return request(`/api/questions/${encodeURIComponent(id)}/images/${encodeURIComponent(assetId)}/replace`, {
    method: 'PUT', body: JSON.stringify(body),
  });
}

export async function updateQuestionImage(id: string, assetId: string, body: Record<string, unknown>): Promise<{ updated: boolean }> {
  return request(`/api/questions/${encodeURIComponent(id)}/images/${encodeURIComponent(assetId)}`, {
    method: 'PATCH', body: JSON.stringify(body),
  });
}

export async function deleteQuestionImage(id: string, assetId: string): Promise<void> {
  await request(`/api/questions/${encodeURIComponent(id)}/images/${encodeURIComponent(assetId)}`, { method: 'DELETE' });
}

export async function reorderQuestionImages(id: string, assetIds: string[]): Promise<void> {
  await request(`/api/questions/${encodeURIComponent(id)}/images/reorder`, {
    method: 'POST', body: JSON.stringify({ asset_ids: assetIds }),
  });
}

export async function validateQuestionImages(id: string): Promise<import('../types').ValidationResponse> {
  return request(`/api/questions/${encodeURIComponent(id)}/images/validate`);
}

export async function fetchAvailableImages(keyword?: string): Promise<{ asset_id: string; filename: string; file_path: string; mime_type: string }[]> {
  const params = keyword ? `?keyword=${encodeURIComponent(keyword)}` : '';
  return request(`/api/questions/images/available${params}`);
}

// 鈹€鈹€ Favorites API 鈹€鈹€

export async function fetchFavoriteGroups(): Promise<import('../types').FavoriteGroupItem[]> {
  return request('/api/favorites/groups');
}

export async function createFavoriteGroup(name: string): Promise<import('../types').FavoriteGroupItem> {
  return request('/api/favorites/groups', { method: 'POST', body: JSON.stringify({ name }) });
}

export async function updateFavoriteGroup(id: string, name: string): Promise<void> {
  await request(`/api/favorites/groups/${encodeURIComponent(id)}`, {
    method: 'PUT', body: JSON.stringify({ name }),
  });
}

export async function deleteFavoriteGroup(id: string): Promise<void> {
  await request(`/api/favorites/groups/${encodeURIComponent(id)}`, { method: 'DELETE' });
}

export async function assignFavorites(
  body: import('../types').FavoriteAssignRequest,
): Promise<import('../types').BatchFavoriteResponse> {
  return request('/api/favorites/assign', { method: 'POST', body: JSON.stringify(body) });
}

export async function batchStarFavorites(
  body: { question_ids: string[]; star_rating: number },
): Promise<import('../types').BatchFavoriteResponse> {
  return request('/api/favorites/batch-star', { method: 'POST', body: JSON.stringify(body) });
}

// 鈹€鈹€ Mistake (閿欓) API 鈹€鈹€

export async function markMistake(questionId: string): Promise<{ question_id: string; status: string; message: string }> {
  return request(`/api/questions/${questionId}/mistake/mark`, { method: 'POST' });
}

export async function unmarkMistake(questionId: string): Promise<{ question_id: string; status: string; message: string }> {
  return request(`/api/questions/${questionId}/mistake/unmark`, { method: 'POST' });
}

export async function batchMarkMistake(questionIds: string[]): Promise<{ total: number; updated: number; skipped: number; failed: number }> {
  return request('/api/questions/mistake/batch-mark', { method: 'POST', body: JSON.stringify({ question_ids: questionIds }) });
}

export async function batchUnmarkMistake(questionIds: string[]): Promise<{ total: number; updated: number; skipped: number; failed: number }> {
  return request('/api/questions/mistake/batch-unmark', { method: 'POST', body: JSON.stringify({ question_ids: questionIds }) });
}

export async function fetchMistakeIds(): Promise<string[]> {
  return request('/api/questions/mistakes');
}

export async function fetchMistakeCount(): Promise<{ count: number }> {
  return request('/api/questions/mistakes/count');
}

export async function removeFromFavorites(questionIds: string[]): Promise<{ removed: number }> {
  return request('/api/favorites/remove', { method: 'POST', body: JSON.stringify(questionIds) });
}

export async function fetchFavoriteItem(questionId: string): Promise<import('../types').FavoriteItemView | null> {
  return request(`/api/favorites/items/${encodeURIComponent(questionId)}`);
}

export async function fetchFavoriteItems(
  groupId?: string, minStar?: number, limit?: number, offset?: number,
): Promise<import('../types').FavoriteItemView[]> {
  const params = new URLSearchParams();
  if (groupId) params.set('group_id', groupId);
  if (minStar) params.set('min_star', String(minStar));
  if (limit) params.set('limit', String(limit));
  if (offset) params.set('offset', String(offset));
  const qs = params.toString();
  return request(`/api/favorites/items${qs ? `?${qs}` : ''}`);
}

export async function fetchFavoriteIds(): Promise<string[]> {
  return request('/api/favorites/ids');
}

// 鈹€鈹€ Collections API 鈹€鈹€

export async function fetchCollectionTree(): Promise<import('../types').CollectionNode[]> {
  return request('/api/collections/tree');
}

export async function fetchCollectionsTree(): Promise<import('../types').Collection[]> {
  return request('/api/collections/tree');
}

export async function createCollection(
  body: { name: string; parent_id?: string | null; type?: string },
): Promise<{ id: string; name: string; parent_id?: string | null; type?: string }> {
  return request('/api/collections', { method: 'POST', body: JSON.stringify(body) });
}

export async function batchMoveQuestions(
  body: import('../types').BatchMoveRequest,
): Promise<import('../types').BatchMoveResponse> {
  return request('/api/collections/batch-move', { method: 'POST', body: JSON.stringify(body) });
}

export async function removeFromCollection(
  body: { question_ids: string[]; collection_id: string },
): Promise<{ removed: number }> {
  return request('/api/collections/remove-questions', { method: 'POST', body: JSON.stringify(body) });
}

export async function fetchQuestionCollections(
  questionId: string,
): Promise<import('../types').CollectionNode[]> {
  return request(`/api/collections/questions/${encodeURIComponent(questionId)}`);
}

// 鈹€鈹€ Batch Analysis API 鈹€鈹€

export async function batchGenerateAnalysis(
  body: import('../types').BatchAnalysisRequest,
): Promise<import('../types').BatchAnalysisResponse> {
  return request('/api/ai/analysis/batch-generate', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

// 鈹€鈹€ Metadata Batch API 鈹€鈹€

export async function batchUpdateMetadata(
  body: import('../types').BatchMetadataRequest,
): Promise<import('../types').BatchMetadataResponse> {
  return request('/api/questions/batch-metadata', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

// 鈹€鈹€ Single-Question AI Generation 鈹€鈹€

export async function generateSingleAnalysis(
  body: { question: Record<string, unknown>; style?: string; include_extension?: boolean; force_regenerate?: boolean },
): Promise<{ question_id: string; analysis_text: string; generated: boolean; warnings: string[] }> {
  return request('/api/ai/analysis/generate', { method: 'POST', body: JSON.stringify(body) });
}

export async function generateKnowledge(
  body: { knowledge_points: string[]; style?: string; length?: string; include_formula?: boolean; include_common_mistakes?: boolean; force_regenerate?: boolean },
): Promise<{ knowledge_key: string; title: string; content: string; outline: string[]; generated: boolean; from_cache: boolean; warnings: string[] }> {
  return request('/api/ai/knowledge/generate', { method: 'POST', body: JSON.stringify(body) });
}

// 鈹€鈹€ Similar Questions API 鈹€鈹€

export async function fetchSimilarQuestions(
  questionId: string,
  limit: number = 10,
): Promise<import('../types').SimilarQuestionsResponse> {
  const params = new URLSearchParams({ limit: String(limit) });
  try {
    const raw = await request<Record<string, unknown>>(
      `/api/questions/${encodeURIComponent(questionId)}/similar?${params}`,
    );
    // Normalise field names: the backend sends similarity_score but some
    // deployments may still use similarity or similarityScore as aliases.
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
      items: items as import('../types').SimilarQuestionItem[],
      total_candidates: (raw.total_candidates as number) || 0,
      limit: (raw.limit as number) || limit,
    };
  } catch (error) {
    if (error instanceof Error && /Not Found|HTTP 404/i.test(error.message)) {
      return {
        question_id: questionId,
        items: [],
        total_candidates: 0,
        limit,
      };
    }
    throw error;
  }
}

// 鈹€鈹€ Import Task Persistence (localStorage) 鈹€鈹€

export async function restorePackage(file: File): Promise<RestorePackageResponse> {
  const formData = new FormData();
  formData.append('file', file);

  const res = await fetch(`${BASE}/api/system/restore-package`, {
    method: 'POST',
    body: formData,
  });

  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: '鎭㈠澶辫触' }));
    const msg =
      typeof error.detail === 'object'
        ? error.detail?.message || JSON.stringify(error.detail)
        : error.detail || '鎭㈠澶辫触';
    throw new Error(msg);
  }

  return res.json();
}

// 鈹€鈹€ Annotation (鎵规敞) API 鈹€鈹€

export async function fetchAnnotations(questionId: string): Promise<import('../types').QuestionAnnotation[]> {
  return request(`/api/questions/${encodeURIComponent(questionId)}/annotations`);
}

export async function createAnnotation(
  questionId: string,
  body: Partial<import('../types').QuestionAnnotation>,
): Promise<import('../types').QuestionAnnotation> {
  return request(`/api/questions/${encodeURIComponent(questionId)}/annotations`, {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export async function updateAnnotation(
  annotationId: string,
  patch: Partial<import('../types').QuestionAnnotation>,
): Promise<import('../types').QuestionAnnotation> {
  return request(`/api/questions/annotations/${encodeURIComponent(annotationId)}`, {
    method: 'PUT',
    body: JSON.stringify(patch),
  });
}

export async function deleteAnnotation(annotationId: string): Promise<{ status: string; annotation_id: string }> {
  return request(`/api/questions/annotations/${encodeURIComponent(annotationId)}`, { method: 'DELETE' });
}

export type {
  AiBatchTask,
  BasketItem,
  CleanDocumentRequest,
  CleanDocumentResponse,
  Collection,
  ConvertDocumentRequest,
  ConvertDocumentResponse,
  ImportBatch,
  ImportPipelineTaskResponse,
  Layout,
  McpConfig,
  ParseStructuredQuestionsRequest,
  ParseStructuredQuestionsResponse,
  Question as QuestionType,
  SystemSettings,
  TaskLog,
  Template,
};
