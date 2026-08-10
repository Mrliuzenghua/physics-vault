import type {
  AssetListResponse,
  CacheCleanupPreviewResponse,
  CleanupPreviewResponse,
  CleanupResponse,
  DeleteAssetResponse,
  ImageListResponse,
  QuestionImageDetail,
  StorageAnalysisResponse,
  ValidationResponse,
} from '../types';
import { request } from './apiClient.ts';

export async function fetchAssetList(
  options: {
    filterMode?: string;
    keyword?: string;
    source?: string;
    batchId?: string;
    sortBy?: string;
    sortOrder?: string;
    page?: number;
    pageSize?: number;
    refresh?: boolean;
  } = {},
): Promise<AssetListResponse> {
  const params = new URLSearchParams({
    filter_mode: options.filterMode ?? 'all',
    keyword: options.keyword ?? '',
    source: options.source ?? 'all',
    batch_id: options.batchId ?? '',
    sort_by: options.sortBy ?? 'modified_at',
    sort_order: options.sortOrder ?? 'desc',
    page: String(options.page ?? 1),
    page_size: String(options.pageSize ?? 60),
    refresh: String(options.refresh ?? false),
  });
  return request(`/api/assets?${params}`);
}

export async function fetchAssetCleanupPreview(): Promise<CleanupPreviewResponse> {
  return request('/api/assets/cleanup-preview');
}

export async function fetchImportCacheCleanupPreview(batchId = ''): Promise<CacheCleanupPreviewResponse> {
  const params = new URLSearchParams({ batch_id: batchId });
  return request(`/api/assets/cache-cleanup-preview?${params}`);
}

export async function cleanupImportCache(batchId = ''): Promise<CleanupResponse> {
  return request('/api/assets/cleanup-import-cache', {
    method: 'POST',
    body: JSON.stringify({ batch_id: batchId || null }),
  });
}

export async function fetchUnusedCacheCleanupPreview(batchId = ''): Promise<CacheCleanupPreviewResponse> {
  const params = new URLSearchParams({ batch_id: batchId });
  return request(`/api/assets/unused-cache-preview?${params}`);
}

export async function cleanupUnusedCache(batchId = ''): Promise<CleanupResponse> {
  return request('/api/assets/cleanup-unused-cache', {
    method: 'POST',
    body: JSON.stringify({ batch_id: batchId || null }),
  });
}

export async function fetchAssetStorageAnalysis(
  source = 'all',
  refresh = false,
): Promise<StorageAnalysisResponse> {
  const params = new URLSearchParams({ source, refresh: String(refresh) });
  return request(`/api/assets/storage-analysis?${params}`);
}

export async function cleanupUnreferencedAssets(): Promise<CleanupResponse> {
  return request('/api/assets/cleanup-unreferenced', { method: 'POST' });
}

export async function deleteSingleAsset(filename: string): Promise<DeleteAssetResponse> {
  return request(`/api/assets/${encodeURIComponent(filename)}`, { method: 'DELETE' });
}

export async function fetchQuestionImages(id: string): Promise<ImageListResponse> {
  return request(`/api/questions/${encodeURIComponent(id)}/images`);
}

export async function addQuestionImage(
  id: string,
  body: { asset_id: string; role?: string; sort_order?: number; placeholder_key?: string; is_primary?: boolean },
): Promise<QuestionImageDetail> {
  return request(`/api/questions/${encodeURIComponent(id)}/images`, {
    method: 'POST', body: JSON.stringify(body),
  });
}

export async function addCachedQuestionImage(
  id: string,
  body: { relative_path: string; role?: string; sort_order?: number; is_primary?: boolean },
): Promise<QuestionImageDetail> {
  return request(`/api/questions/${encodeURIComponent(id)}/images/from-cache`, {
    method: 'POST', body: JSON.stringify(body),
  });
}

export async function replaceQuestionImage(
  id: string,
  assetId: string,
  body: { old_asset_id: string; new_asset_id: string },
): Promise<QuestionImageDetail> {
  return request(`/api/questions/${encodeURIComponent(id)}/images/${encodeURIComponent(assetId)}/replace`, {
    method: 'PUT', body: JSON.stringify(body),
  });
}

export async function updateQuestionImage(
  id: string,
  assetId: string,
  body: Record<string, unknown>,
): Promise<{ updated: boolean }> {
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

export async function validateQuestionImages(id: string): Promise<ValidationResponse> {
  return request(`/api/questions/${encodeURIComponent(id)}/images/validate`);
}

export async function fetchAvailableImages(keyword?: string): Promise<{
  asset_id: string;
  filename: string;
  file_path: string;
  mime_type: string;
}[]> {
  const params = keyword ? `?keyword=${encodeURIComponent(keyword)}` : '';
  return request(`/api/questions/images/available${params}`);
}
