import type { Question } from '../types';
import { request } from './apiClient.ts';

export interface DatabaseStatus {
  questions_count: number;
}

export async function fetchDatabaseStatus(): Promise<DatabaseStatus> { return request('/api/system/db-status'); }
export async function fetchImages(params: Record<string, string>): Promise<unknown[]> { return request(`/images?${new URLSearchParams(params)}`); }
export async function fetchPapers(): Promise<unknown[]> { return request('/papers'); }
export async function fetchPaperQuestions(paperId: string): Promise<Question[]> { return request(`/papers/${encodeURIComponent(paperId)}/questions`); }
export async function fetchReviewQueue(): Promise<Question[]> { return request('/review-queue'); }
export async function fetchEmbeddingStatus(): Promise<unknown> { return request('/embeddings/status'); }
export async function healthCheck(): Promise<{ status: string }> { return request('/health'); }
