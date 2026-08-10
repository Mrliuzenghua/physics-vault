import type {
  ReviewDraftLookupResponse,
  ReviewDraftResponse,
  ReviewDraftVersionListResponse,
  SaveReviewDraftRequest,
} from '../types';
import { request, requestResponse } from './apiClient.ts';

export class ReviewDraftConflictError extends Error {
  current: ReviewDraftResponse | null;

  constructor(current: ReviewDraftResponse | null) {
    super('服务器草稿已更新，请先处理版本冲突');
    this.name = 'ReviewDraftConflictError';
    this.current = current;
  }
}

export async function fetchReviewDraft(taskId: string): Promise<ReviewDraftLookupResponse> {
  return request(`/api/review/drafts/${encodeURIComponent(taskId)}`);
}

export async function saveReviewDraft(
  taskId: string,
  body: SaveReviewDraftRequest,
): Promise<ReviewDraftResponse> {
  const response = await requestResponse(`/api/review/drafts/${encodeURIComponent(taskId)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }, [409]);
  if (response.status === 409) {
    const payload = await response.json().catch(() => null) as { detail?: { current?: ReviewDraftResponse | null } } | null;
    throw new ReviewDraftConflictError(payload?.detail?.current ?? null);
  }
  return response.json();
}

export async function fetchReviewDraftVersions(
  taskId: string,
  limit = 20,
): Promise<ReviewDraftVersionListResponse> {
  return request(`/api/review/drafts/${encodeURIComponent(taskId)}/versions?limit=${limit}`);
}

export async function deleteReviewDraft(taskId: string): Promise<void> {
  await request(`/api/review/drafts/${encodeURIComponent(taskId)}`, { method: 'DELETE' });
}

export async function restoreReviewDraftVersion(
  taskId: string,
  version: number,
  baseVersion: number,
): Promise<ReviewDraftResponse> {
  return request(`/api/review/drafts/${encodeURIComponent(taskId)}/restore`, {
    method: 'POST',
    body: JSON.stringify({ version, base_version: baseVersion }),
  });
}
