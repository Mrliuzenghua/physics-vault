import type {
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
  Question,
  SystemSettings,
  Template,
} from '../types';
import { request } from './apiClient';

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
  fetchQuestion,
  fetchQuestionAssets,
  fetchQuestionVersionDetail,
  fetchQuestionVersions,
  fetchQuestionsByIds,
  fetchSimilarQuestions,
  returnQuestionToReview,
  rollbackQuestionVersion,
  searchQuestions,
  updateQuestion,
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
export {
  deleteAnnotation,
  createAnnotation,
  fetchAnnotations,
  updateAnnotation,
} from './annotationsApi';
export {
  batchUpdateMetadata,
  fetchKnowledgePointCounts,
  fetchKnowledgePoints,
  fetchQuestionKnowledgePoints,
  generateKnowledge,
  updateQuestionKnowledgePoints,
} from './metadataApi';
export {
  deleteReviewDraft,
  fetchReviewDraft,
  fetchReviewDraftVersions,
  restoreReviewDraftVersion,
  ReviewDraftConflictError,
  saveReviewDraft,
} from './reviewDraftApi';
export {
  batchGenerateAnalysis,
  completeImportDraftMetadata,
  deleteReviewTask,
  fastCleanReviewLatex,
  fetchBatchImages,
  fetchReviewTasks,
  generateSingleAnalysis,
  saveReviewedKnowledge,
  saveReviewedQuestions,
  submitAiGeneratedReview,
  uploadBatchImage,
} from './reviewApi';
export {
  createImportBatch,
  extractBatchImages,
  fetchImportBatchOverview,
  fetchImportBatchStatus,
  fetchImportTask,
  retrySavedImportBatch,
  runImportBatchAiClean,
  runImportBatchAiRefine,
  runImportBatchAiStructure,
  runImportBatchPandoc,
  runImportBatchRecognize,
  uploadImportFile,
} from './importApi';
export type { ImportBatchStatus, PersistedImportBatchSummary } from './importApi';
export {
  completeQuestionAnalysis,
  fetchAgentConfig,
  fetchMcpRuntimeConfig,
  fetchMcpStatus,
  refineQuestionFormat,
  runQuestionPickerAgent,
  saveAgentConfig,
  sendAiAssistantChat,
  sendAiChatTest,
  streamQuestionPickerAgent,
  testClaudeCodeAgent,
  testMcpConnection,
} from './aiApi';
export {
  fetchLatestPaperDraft,
  fetchPaperDraft,
  listPaperDrafts,
  savePaperDraft,
} from './paperDraftApi';
export {
  fetchQuestionImageCache,
  uploadQuestionImageCache,
} from './imageCacheApi';
export type { ImageCacheAsset } from './imageCacheApi';

export interface DatabaseStatus {
  questions_count: number;
}

export async function fetchDatabaseStatus(): Promise<DatabaseStatus> {
  return request('/api/system/db-status');
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
