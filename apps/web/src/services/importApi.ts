import type {
  AiCleanBatchResponse,
  AiParseDocumentRequest,
  AiParseDocumentResponse,
  AiRefineBatchResponse,
  AiStructureBatchResponse,
  CleanDocumentRequest,
  CleanDocumentResponse,
  ConvertDocumentRequest,
  ConvertDocumentResponse,
  ExtractBatchImagesResponse,
  ImportBatchResponse,
  ImportPipelineTaskResponse,
  ImportMediaAsset,
  PandocBatchResponse,
  RecognizeBatchResponse,
  ParseStructuredQuestionsRequest,
  ParseStructuredQuestionsResponse,
  UploadImportFileResponse,
} from '../types';
import { request, requestForm } from './apiClient.ts';

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

export async function fetchImportTask(taskId: string): Promise<ImportPipelineTaskResponse> {
  return request(`/api/import/tasks/${encodeURIComponent(taskId)}`);
}

async function waitForImportTask(initialTask: ImportPipelineTaskResponse, timeoutMs = 30 * 60 * 1000): Promise<ImportPipelineTaskResponse> {
  let task = initialTask;
  const deadline = Date.now() + timeoutMs;
  while (['pending', 'running', 'retrying', 'cancel_requested'].includes(task.status)) {
    if (Date.now() >= deadline) throw new Error('后台任务仍在运行，可稍后从导入记录中继续查看');
    await new Promise((resolve) => window.setTimeout(resolve, 1000));
    task = await fetchImportTask(task.task_id);
  }
  if (task.status === 'failed') throw new Error(task.error || '后台任务执行失败');
  if (task.status === 'cancelled') throw new Error('后台任务已取消');
  return task;
}

async function runQueuedBatchStage<T>(batchId: string, stage: string): Promise<T> {
  let initialTask: ImportPipelineTaskResponse;
  try {
    initialTask = await request(`/api/import/batches/${encodeURIComponent(batchId)}/${stage}-task`, { method: 'POST' });
  } catch (submissionError) {
    const status = await fetchImportBatchStatus(batchId).catch(() => null);
    const expectedOperation = stage.replaceAll('-', '_');
    if (!status?.active_task_id || status.active_operation !== expectedOperation) throw submissionError;
    initialTask = await fetchImportTask(status.active_task_id);
  }
  const task = await waitForImportTask(initialTask);
  if (!task.result) throw new Error('后台任务完成但没有返回结果');
  return task.result as T;
}

export async function runImportBatchPandoc(batchId: string): Promise<PandocBatchResponse> { return runQueuedBatchStage(batchId, 'pandoc'); }
export async function runImportBatchAiClean(batchId: string): Promise<AiCleanBatchResponse> { return runQueuedBatchStage(batchId, 'ai-clean'); }
export async function runImportBatchAiStructure(batchId: string): Promise<AiStructureBatchResponse> { return runQueuedBatchStage(batchId, 'ai-structure'); }
export async function runImportBatchRecognize(batchId: string): Promise<RecognizeBatchResponse> { return runQueuedBatchStage(batchId, 'recognize'); }

export async function extractBatchImages(batchId: string): Promise<ExtractBatchImagesResponse> {
  return request(`/api/import/batches/${encodeURIComponent(batchId)}/extract-images`, { method: 'POST' });
}

export async function runImportBatchAiRefine(batchId: string, questions: Record<string, unknown>[]): Promise<AiRefineBatchResponse> {
  return request(`/api/import/batches/${encodeURIComponent(batchId)}/ai-refine`, { method: 'POST', body: JSON.stringify({ questions }) });
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

/** Confirm user-edited questions and return the review workbench task. */
export async function confirmImportBatch(
  batchId: string,
  questions: Record<string, unknown>[],
  inputVersion?: number,
  mediaAssets: ImportMediaAsset[] = [],
): Promise<{ task_id: string; batch_id: string; question_count: number }> {
  return request(`/api/import/batches/${encodeURIComponent(batchId)}/confirm`, {
    method: 'POST', body: JSON.stringify({ questions, input_version: inputVersion, media_assets: mediaAssets }),
  });
}

export async function convertDocument(body: ConvertDocumentRequest): Promise<ConvertDocumentResponse> {
  return request('/api/import/convert', { method: 'POST', body: JSON.stringify(body) });
}

export async function cleanDocument(body: CleanDocumentRequest): Promise<CleanDocumentResponse> {
  return request('/api/import/clean', { method: 'POST', body: JSON.stringify(body) });
}

export async function parseStructuredQuestions(body: ParseStructuredQuestionsRequest): Promise<ParseStructuredQuestionsResponse> {
  return request('/api/import/parse', { method: 'POST', body: JSON.stringify(body) });
}

export async function importQuestion(body: {
  classification: Record<string, unknown>; source: Record<string, unknown>; content: Record<string, unknown>;
  images?: Array<Record<string, unknown>>; knowledge_points?: Array<Record<string, unknown>>;
  metadata?: Record<string, unknown>; reviewer?: string; note?: string;
}): Promise<{ question_id: string; status: string; knowledge_points_inserted: number; images_linked: number; skipped_knowledge_points: string[]; review_id: string }> {
  return request('/questions/import', { method: 'POST', body: JSON.stringify(body) });
}

export async function aiParseDocument(body: AiParseDocumentRequest): Promise<AiParseDocumentResponse> {
  return request('/api/import/ai-parse-document', { method: 'POST', body: JSON.stringify(body) });
}
