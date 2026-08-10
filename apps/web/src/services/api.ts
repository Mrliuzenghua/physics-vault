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
  aiParseDocument,
  cleanDocument,
  confirmImportBatch,
  convertDocument,
  createImportBatch,
  extractBatchImages,
  fetchImportBatchOverview,
  fetchImportBatchStatus,
  fetchImportTask,
  importQuestion,
  parseStructuredQuestions,
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
export {
  fetchDatabaseStatus,
  fetchEmbeddingStatus,
  fetchImages,
  fetchPaperQuestions,
  fetchPapers,
  fetchReviewQueue,
  healthCheck,
} from './catalogApi';
export type { DatabaseStatus } from './catalogApi';

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
