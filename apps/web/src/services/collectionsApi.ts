import type { BatchMoveRequest, BatchMoveResponse, Collection, CollectionNode } from '../types';
import { request } from './apiClient.ts';

export async function fetchCollectionTree(): Promise<CollectionNode[]> {
  return request('/api/collections/tree');
}

export async function fetchCollectionsTree(): Promise<Collection[]> {
  return request('/api/collections/tree');
}

export async function createCollection(
  body: { name: string; parent_id?: string | null; type?: string },
): Promise<{ id: string; name: string; parent_id?: string | null; type?: string }> {
  return request('/api/collections', { method: 'POST', body: JSON.stringify(body) });
}

export async function batchMoveQuestions(body: BatchMoveRequest): Promise<BatchMoveResponse> {
  return request('/api/collections/batch-move', { method: 'POST', body: JSON.stringify(body) });
}

export async function removeFromCollection(
  body: { question_ids: string[]; collection_id: string },
): Promise<{ removed: number }> {
  return request('/api/collections/remove-questions', { method: 'POST', body: JSON.stringify(body) });
}

export async function fetchQuestionCollections(questionId: string): Promise<CollectionNode[]> {
  return request(`/api/collections/questions/${encodeURIComponent(questionId)}`);
}
