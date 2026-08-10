import type { BatchFavoriteResponse, FavoriteAssignRequest, FavoriteGroupItem, FavoriteItemView } from '../types';
import { request } from './apiClient.ts';

export async function fetchFavoriteGroups(): Promise<FavoriteGroupItem[]> {
  return request('/api/favorites/groups');
}

export async function createFavoriteGroup(name: string): Promise<FavoriteGroupItem> {
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

export async function assignFavorites(body: FavoriteAssignRequest): Promise<BatchFavoriteResponse> {
  return request('/api/favorites/assign', { method: 'POST', body: JSON.stringify(body) });
}

export async function batchStarFavorites(
  body: { question_ids: string[]; star_rating: number },
): Promise<BatchFavoriteResponse> {
  return request('/api/favorites/batch-star', { method: 'POST', body: JSON.stringify(body) });
}

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

export async function fetchFavoriteItem(questionId: string): Promise<FavoriteItemView | null> {
  return request(`/api/favorites/items/${encodeURIComponent(questionId)}`);
}

export async function fetchFavoriteItems(
  groupId?: string, minStar?: number, limit?: number, offset?: number,
): Promise<FavoriteItemView[]> {
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
