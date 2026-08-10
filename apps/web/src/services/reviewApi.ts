import type {
  AiGeneratedReviewRequest,
  AiGeneratedReviewResponse,
  BatchAnalysisRequest,
  BatchAnalysisResponse,
  DeleteReviewTaskResponse,
  DraftMetadataRequest,
  DraftMetadataResponse,
  ImportMediaAsset,
  ReviewLatexCleanupResponse,
  ReviewTaskListResponse,
  SaveReviewedKnowledgeRequest,
  SaveReviewedKnowledgeResponse,
  SaveReviewedQuestionsRequest,
  SaveReviewedQuestionsResponse,
} from '../types';
import { fetchAssetList } from './assetsApi.ts';
import { request, requestForm } from './apiClient.ts';

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

export async function completeImportDraftMetadata(
  batchId: string,
  body: DraftMetadataRequest,
): Promise<DraftMetadataResponse> {
  return request(`/api/import/batches/${encodeURIComponent(batchId)}/draft-metadata`, {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export async function submitAiGeneratedReview(
  body: AiGeneratedReviewRequest,
): Promise<AiGeneratedReviewResponse> {
  return request('/api/import/ai-generated-review', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export async function fetchReviewTasks(limit = 80): Promise<ReviewTaskListResponse> {
  return request(`/api/import/review-tasks?limit=${limit}`);
}

export async function deleteReviewTask(taskId: string): Promise<DeleteReviewTaskResponse> {
  return request(`/api/import/review-tasks/${encodeURIComponent(taskId)}`, {
    method: 'DELETE',
  });
}

export async function uploadBatchImage(batchId: string, file: File): Promise<ImportMediaAsset> {
  const formData = new FormData();
  formData.append('file', file);
  return requestForm(`/api/import/batches/${encodeURIComponent(batchId)}/images`, formData);
}

export async function fetchBatchImages(batchId: string): Promise<ImportMediaAsset[]> {
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

export async function saveReviewedQuestions(
  body: SaveReviewedQuestionsRequest,
): Promise<SaveReviewedQuestionsResponse> {
  return request('/api/review/save', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export async function saveReviewedKnowledge(
  body: SaveReviewedKnowledgeRequest,
): Promise<SaveReviewedKnowledgeResponse> {
  return request('/api/review/save-knowledge', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export async function batchGenerateAnalysis(body: BatchAnalysisRequest): Promise<BatchAnalysisResponse> {
  return request('/api/ai/analysis/batch-generate', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export async function generateSingleAnalysis(
  body: { question: Record<string, unknown>; style?: string; include_extension?: boolean; force_regenerate?: boolean },
): Promise<{ question_id: string; analysis_text: string; generated: boolean; warnings: string[] }> {
  return request('/api/ai/analysis/generate', { method: 'POST', body: JSON.stringify(body) });
}
