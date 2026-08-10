import type {
  AiBatchTask,
  AiChatMessage,
  AiChatTestResponse,
  AiAssistantResponse,
  AgentStreamEvent,
  AgentConfig,
  AgentConfigResponse,
  AgentTestResponse,
  BasketItem,
  CleanDocumentRequest,
  CleanDocumentResponse,
  Collection,
  ConvertDocumentRequest,
  ConvertDocumentResponse,
  ImportBatch,
  ImportBatchResponse,
  ImportPipelineTaskResponse,
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
  QuestionPickerAgentResponse,
  RecognizeBatchResponse,
  ReviewLatexCleanupResponse,
  SystemSettings,
  Template,
  UploadImportFileResponse,
} from '../types';
import { ApiError, request, requestForm, requestResponse } from './apiClient';
import { fetchAssetList } from './assetsApi';

export {
  DEFAULT_AI_CONFIG,
  addToBasket,
  clearBasket,
  getBasket,
  getMcpConfig,
  getSettings,
  getTheme,
  moveBasketItem,
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
export {
  cancelTask,
  downloadTaskResult,
  fetchProcessingRuns,
  fetchTask,
  fetchTaskStageEvents,
  fetchTasks,
  retryTask,
} from './taskApi';
export {
  fetchChangeBatch,
  fetchChangeBatches,
  rollbackChangeBatch,
} from './auditApi';
export { downloadExportPackage, restorePackage } from './systemPackageApi';
export {
  archiveTeachingProject,
  duplicateTeachingProject,
  fetchTeachingProject,
  listTeachingProjects,
  saveTeachingProjectSnapshot,
} from './teachingProjectApi';
export { listLessonReflections, saveLessonReflection } from './lessonReflectionApi';
export {
  fetchSavedHandout,
  listSavedHandoutVersions,
  listSavedHandoutsFromServer,
  renameSavedHandout,
  restoreSavedHandoutVersion,
  saveSavedLessonPackage,
} from './lessonDocumentApi';
export {
  deleteQuestions,
  fetchFacets,
  fetchKnowledgePointCounts,
  fetchKnowledgePoints,
  fetchQuestion,
  fetchQuestionAssets,
  fetchQuestionKnowledgePoints,
  fetchQuestionVersionDetail,
  fetchQuestionVersions,
  fetchQuestionsByIds,
  returnQuestionToReview,
  rollbackQuestionVersion,
  searchQuestions,
  updateQuestion,
  updateQuestionKnowledgePoints,
} from './questionApi';
export {
  addCachedQuestionImage,
  addQuestionImage,
  cleanupImportCache,
  cleanupUnreferencedAssets,
  cleanupUnusedCache,
  deleteQuestionImage,
  deleteSingleAsset,
  fetchAssetCleanupPreview,
  fetchAssetList,
  fetchAssetStorageAnalysis,
  fetchAvailableImages,
  fetchImportCacheCleanupPreview,
  fetchQuestionImages,
  fetchUnusedCacheCleanupPreview,
  reorderQuestionImages,
  replaceQuestionImage,
  updateQuestionImage,
  validateQuestionImages,
} from './assetsApi';
export {
  assignFavorites,
  batchMarkMistake,
  batchStarFavorites,
  batchUnmarkMistake,
  createFavoriteGroup,
  deleteFavoriteGroup,
  fetchFavoriteGroups,
  fetchFavoriteIds,
  fetchFavoriteItem,
  fetchFavoriteItems,
  fetchMistakeCount,
  fetchMistakeIds,
  markMistake,
  removeFromFavorites,
  unmarkMistake,
  updateFavoriteGroup,
} from './favoritesApi';
export {
  batchMoveQuestions,
  createCollection,
  fetchCollectionsTree,
  fetchCollectionTree,
  fetchQuestionCollections,
  removeFromCollection,
} from './collectionsApi';

export interface DatabaseStatus {
  questions_count: number;
}

export async function fetchDatabaseStatus(): Promise<DatabaseStatus> {
  return request('/api/system/db-status');
}

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
        id: node.id,
        type: 'question',
        position,
        question_id: node.questionId,
        title: question?.title || question?.canonical_title || node.questionId,
        score: estimateQuestionScore(question?.question_type),
        payload: {
          question_type: question?.question_type,
          difficulty: question?.difficulty,
          source: question?.source || question?.origin_file || question?.primary_paper_id,
          // A composition item is an editable project-level question instance.
          // Keep the complete snapshot so reopening a draft never replaces
          // teacher edits with the current question-bank record.
          question_snapshot: question ? { ...question } : undefined,
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
      base_updated_at: baseUpdatedAt,
      title: pkg.title,
      subtitle: pkg.subtitle,
      source: pkg.source,
      status: 'draft',
      items,
      metadata: {
        documentRevision,
        headerFooter: pkg.headerFooter,
        styleConfig: pkg.styleConfig,
        formatSpec: pkg.formatSpec,
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

export async function fetchEmbeddingStatus(): Promise<unknown> {
  return request('/embeddings/status');
}

export async function healthCheck(): Promise<{ status: string }> {
  return request('/health');
}

// MCP runtime

export async function fetchMcpStatus(): Promise<import('../types').McpRuntimeStatus> {
  return request('/api/mcp/status');
}

export async function fetchMcpRuntimeConfig(): Promise<{
  vl: McpConfig['vl'];
  llm: McpConfig['llm'];
  vl_configured: boolean;
  llm_configured: boolean;
}> {
  return request('/api/mcp/config');
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

export async function refineQuestionFormat(question: Question): Promise<Partial<Question>> {
  const result = await request<{ ok: boolean; data: Partial<Question> }>('/api/mcp/refine-question-format', {
    method: 'POST',
    body: JSON.stringify({ question }),
  });
  return result.data;
}

export async function completeQuestionAnalysis(question: Question): Promise<string> {
  const difficulty = Number(question.difficulty);
  const result = await request<{ ok: boolean; data: { analysis_text?: string; analysis?: string } }>('/api/mcp/generate-analysis', {
    method: 'POST',
    body: JSON.stringify({
      question: {
        question_id: question.question_id,
        question_type: question.question_type || 'calculation',
        title: question.title || '',
        options: question.options || [],
        answer: question.answer || '',
        analysis: question.analysis || '',
        figures: (question.figures || []).map((figure) => ({
          fig_uuid: figure.fig_uuid,
          local_path: figure.local_path,
        })),
        difficulty: Number.isInteger(difficulty) && difficulty >= 1 && difficulty <= 5 ? difficulty : null,
        knowledge_point: question.knowledge_point || null,
        tags: question.tags || [],
        source: question.source || null,
      },
      style: 'exam_standard',
      include_extension: false,
    }),
  });
  const analysis = String(result.data.analysis_text || result.data.analysis || '').trim();
  if (!analysis) throw new Error('DeepSeek 没有返回可用解析，请检查题干、答案和模型配置。');
  return analysis;
}

// Import pipeline

export async function uploadImportFile(file: File): Promise<UploadImportFileResponse> {
  const formData = new FormData();
  formData.append('file', file);
  return requestForm('/api/import/upload', formData);
}

export async function createImportBatch(file: File): Promise<ImportBatchResponse> {
  const formData = new FormData();
  formData.append('file', file);
  return requestForm('/api/import/batches', formData);
}

async function waitForImportTask(
  initialTask: ImportPipelineTaskResponse,
  timeoutMs = 30 * 60 * 1000,
): Promise<ImportPipelineTaskResponse> {
  let task = initialTask;
  const deadline = Date.now() + timeoutMs;
  while (
    task.status === 'pending'
    || task.status === 'running'
    || task.status === 'retrying'
    || task.status === 'cancel_requested'
  ) {
    if (Date.now() >= deadline) {
      throw new Error('后台任务仍在运行，可稍后从导入记录中继续查看');
    }
    await new Promise((resolve) => window.setTimeout(resolve, 1000));
    task = await fetchImportTask(task.task_id);
  }
  if (task.status === 'failed') {
    throw new Error(task.error || '后台任务执行失败');
  }
  if (task.status === 'cancelled') {
    throw new Error('后台任务已取消');
  }
  return task;
}

async function runQueuedBatchStage<T>(batchId: string, stage: string): Promise<T> {
  let initialTask: ImportPipelineTaskResponse;
  try {
    initialTask = await request<ImportPipelineTaskResponse>(
      `/api/import/batches/${encodeURIComponent(batchId)}/${stage}-task`,
      { method: 'POST' },
    );
  } catch (submissionError) {
    // The server may have accepted the job before the connection dropped.
    // Recover the durable task id instead of submitting the same work again.
    const status = await fetchImportBatchStatus(batchId).catch(() => null);
    const expectedOperation = stage.replaceAll('-', '_');
    if (!status?.active_task_id || status.active_operation !== expectedOperation) {
      throw submissionError;
    }
    initialTask = await fetchImportTask(status.active_task_id);
  }
  const task = await waitForImportTask(initialTask);
  if (!task.result) throw new Error('后台任务完成但没有返回结果');
  return task.result as T;
}

export async function runImportBatchPandoc(batchId: string): Promise<PandocBatchResponse> {
  return runQueuedBatchStage<PandocBatchResponse>(batchId, 'pandoc');
}

export async function runImportBatchAiClean(batchId: string): Promise<AiCleanBatchResponse> {
  return runQueuedBatchStage<AiCleanBatchResponse>(batchId, 'ai-clean');
}

export async function runImportBatchAiStructure(batchId: string): Promise<AiStructureBatchResponse> {
  return runQueuedBatchStage<AiStructureBatchResponse>(batchId, 'ai-structure');
}

export async function runImportBatchRecognize(batchId: string): Promise<RecognizeBatchResponse> {
  return runQueuedBatchStage<RecognizeBatchResponse>(batchId, 'recognize');
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

export interface PersistedImportBatchSummary {
  batch_id: string;
  source: string;
  original_filename: string;
  status: string;
  question_count: number;
  image_count: number;
  duplicate_count: number;
  updated_at: string;
  created_at: string;
  error?: string | null;
  retryable: boolean;
  active_task_id?: string | null;
  active_operation?: string | null;
  content_version: number;
}

export interface ImportBatchStatus {
  batch_id: string;
  status: string;
  content_version: number;
  active_task_id?: string | null;
  active_operation?: string | null;
}

export async function fetchImportBatchStatus(batchId: string): Promise<ImportBatchStatus> {
  return request(`/api/import/batches/${encodeURIComponent(batchId)}`);
}

export async function fetchImportBatchOverview(limit = 80): Promise<PersistedImportBatchSummary[]> {
  const result = await request<{ items: PersistedImportBatchSummary[] }>(`/api/import/batches?limit=${limit}`);
  return result.items ?? [];
}

export async function retrySavedImportBatch(batchId: string): Promise<RecognizeBatchResponse> {
  return request(`/api/import/batches/${encodeURIComponent(batchId)}/retry`, { method: 'POST' });
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

export async function fetchAgentConfig(): Promise<AgentConfigResponse> {
  return request('/api/agents/config');
}

export async function saveAgentConfig(config: AgentConfig): Promise<AgentConfigResponse> {
  return request('/api/agents/config', {
    method: 'POST',
    body: JSON.stringify(config),
  });
}

export async function testClaudeCodeAgent(): Promise<AgentTestResponse> {
  return request('/api/agents/test-claude-code', { method: 'POST' });
}

export async function fastCleanReviewLatex(body: {
  task_id?: string;
  user_text?: string;
  dry_run?: boolean;
}): Promise<ReviewLatexCleanupResponse> {
  return request('/api/agents/review-latex-cleanup', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export async function runQuestionPickerAgent(
  messages: AiChatMessage[],
  options?: {
    query?: string;
    contextLimit?: number;
    contextQuestionIds?: string[];
    sessionId?: string;
    resumeSession?: boolean;
  },
): Promise<QuestionPickerAgentResponse> {
  return request('/api/agents/question-picker', {
    method: 'POST',
    body: JSON.stringify({
      messages,
      query: options?.query,
      context_limit: options?.contextLimit ?? 12,
      context_question_ids: options?.contextQuestionIds ?? [],
      session_id: options?.sessionId,
      resume_session: options?.resumeSession ?? false,
    }),
  });
}

export async function streamQuestionPickerAgent(
  messages: AiChatMessage[],
  options: {
    query?: string;
    contextLimit?: number;
    contextQuestionIds?: string[];
    sessionId?: string;
    resumeSession?: boolean;
    signal?: AbortSignal;
    onEvent: (event: AgentStreamEvent) => void;
  },
): Promise<void> {
  const res = await requestResponse('/api/agents/question-picker/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    signal: options.signal,
    body: JSON.stringify({
      messages,
      query: options.query,
      context_limit: options.contextLimit ?? 12,
      context_question_ids: options.contextQuestionIds ?? [],
      session_id: options.sessionId,
      resume_session: options.resumeSession ?? false,
    }),
  });

  if (!res.body) {
    throw new Error('浏览器没有返回可读取的智能体事件流');
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder('utf-8');
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() ?? '';
    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed) continue;
      options.onEvent(JSON.parse(trimmed) as AgentStreamEvent);
    }
  }

  buffer += decoder.decode();
  const trimmed = buffer.trim();
  if (trimmed) {
    options.onEvent(JSON.parse(trimmed) as AgentStreamEvent);
  }
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
  inputVersion?: number,
  mediaAssets: import('../types').ImportMediaAsset[] = [],
): Promise<{ task_id: string; batch_id: string; question_count: number }> {
  return request(`/api/import/batches/${encodeURIComponent(batchId)}/confirm`, {
    method: 'POST',
    body: JSON.stringify({ questions, input_version: inputVersion, media_assets: mediaAssets }),
  });
}

export async function submitAiGeneratedReview(
  body: import('../types').AiGeneratedReviewRequest,
): Promise<import('../types').AiGeneratedReviewResponse> {
  return request('/api/import/ai-generated-review', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export async function fetchReviewTasks(limit = 80): Promise<import('../types').ReviewTaskListResponse> {
  return request(`/api/import/review-tasks?limit=${limit}`);
}

export async function deleteReviewTask(taskId: string): Promise<import('../types').DeleteReviewTaskResponse> {
  return request(`/api/import/review-tasks/${encodeURIComponent(taskId)}`, {
    method: 'DELETE',
  });
}

/** Upload an extra image into the batch media library. */
export async function uploadBatchImage(
  batchId: string,
  file: File,
): Promise<import('../types').ImportMediaAsset> {
  const formData = new FormData();
  formData.append('file', file);
  return requestForm(`/api/import/batches/${encodeURIComponent(batchId)}/images`, formData);
}

export interface ImageCacheAsset {
  relative_path: string;
  filename: string;
  file_path: string;
  mime_type: string;
  size: number;
}

export async function fetchQuestionImageCache(keyword = '', limit = 200): Promise<ImageCacheAsset[]> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (keyword.trim()) params.set('keyword', keyword.trim());
  return request(`/api/questions/images/cache?${params.toString()}`);
}

export async function uploadQuestionImageCache(files: File[]): Promise<{
  images: ImageCacheAsset[];
  skipped: string[];
}> {
  const formData = new FormData();
  files.forEach((file) => formData.append('files', file));
  return requestForm('/api/questions/images/cache-upload', formData);
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

// Review save

export async function saveReviewedQuestions(
  body: import('../types').SaveReviewedQuestionsRequest,
): Promise<import('../types').SaveReviewedQuestionsResponse> {
  return request('/api/review/save', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export async function fetchBatchImages(batchId: string): Promise<import('../types').ImportMediaAsset[]> {
  try {
    return await request(`/api/import/batches/${encodeURIComponent(batchId)}/images`);
  } catch {
    // Keep historical batches usable while an older API process is still running.
    const result = await fetchAssetList({ source: 'all', batchId, pageSize: 200 });
    return result.assets
      .filter((asset) => asset.batch_id === batchId)
      .map((asset) => ({
        image_id: asset.filename || asset.relative_path,
        filename: asset.filename,
        relative_path: asset.relative_path,
        absolute_path: '',
        size: asset.size_bytes,
      }));
  }
}

export async function saveReviewedKnowledge(
  body: import('../types').SaveReviewedKnowledgeRequest,
): Promise<import('../types').SaveReviewedKnowledgeResponse> {
  return request('/api/review/save-knowledge', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export class ReviewDraftConflictError extends Error {
  current: import('../types').ReviewDraftResponse | null;

  constructor(current: import('../types').ReviewDraftResponse | null) {
    super('服务器草稿已更新，请先处理版本冲突');
    this.name = 'ReviewDraftConflictError';
    this.current = current;
  }
}

export async function fetchReviewDraft(taskId: string): Promise<import('../types').ReviewDraftLookupResponse> {
  return request(`/api/review/drafts/${encodeURIComponent(taskId)}`);
}

export async function saveReviewDraft(
  taskId: string,
  body: import('../types').SaveReviewDraftRequest,
): Promise<import('../types').ReviewDraftResponse> {
  const response = await requestResponse(`/api/review/drafts/${encodeURIComponent(taskId)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }, [409]);
  if (response.status === 409) {
    const payload = await response.json().catch(() => null) as { detail?: { current?: import('../types').ReviewDraftResponse | null } } | null;
    throw new ReviewDraftConflictError(payload?.detail?.current ?? null);
  }
  return response.json();
}

export async function fetchReviewDraftVersions(
  taskId: string,
  limit = 20,
): Promise<import('../types').ReviewDraftVersionListResponse> {
  return request(`/api/review/drafts/${encodeURIComponent(taskId)}/versions?limit=${limit}`);
}

export async function deleteReviewDraft(taskId: string): Promise<void> {
  await request(`/api/review/drafts/${encodeURIComponent(taskId)}`, { method: 'DELETE' });
}

export async function restoreReviewDraftVersion(
  taskId: string,
  version: number,
  baseVersion: number,
): Promise<import('../types').ReviewDraftResponse> {
  return request(`/api/review/drafts/${encodeURIComponent(taskId)}/restore`, {
    method: 'POST',
    body: JSON.stringify({ version, base_version: baseVersion }),
  });
}

// Batch analysis

export async function batchGenerateAnalysis(
  body: import('../types').BatchAnalysisRequest,
): Promise<import('../types').BatchAnalysisResponse> {
  return request('/api/ai/analysis/batch-generate', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

// Metadata batch

export async function batchUpdateMetadata(
  body: import('../types').BatchMetadataRequest,
): Promise<import('../types').BatchMetadataResponse> {
  return request('/api/questions/batch-metadata', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

// Single-question AI generation

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

// Similar questions

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

// Annotations

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
  Template,
};
