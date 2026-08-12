import type { Question } from '../types';
import { request } from './apiClient.ts';

export interface DatabaseStatus {
  questions_count: number;
  browsable_questions_count?: number;
}

export interface CatalogHealthSample {
  question_id: string;
  title: string;
}

export interface CatalogHealthIssue {
  code: string;
  label: string;
  description: string;
  severity: 'danger' | 'warning';
  count: number;
  sample_questions: CatalogHealthSample[];
}

export interface CatalogHealthReport {
  total_questions: number;
  healthy_questions: number;
  questions_needing_attention: number;
  score: number;
  archived_duplicate_count: number;
  issues: CatalogHealthIssue[];
}

export async function fetchDatabaseStatus(): Promise<DatabaseStatus> { return request('/api/system/db-status'); }
export async function fetchCatalogHealth(): Promise<CatalogHealthReport> { return request('/api/system/catalog-health'); }
export async function fetchImages(params: Record<string, string>): Promise<unknown[]> { return request(`/api/images?${new URLSearchParams(params)}`); }
export async function fetchPapers(): Promise<unknown[]> { return request('/api/papers'); }
export async function fetchPaperQuestions(paperId: string): Promise<Question[]> { return request(`/api/papers/${encodeURIComponent(paperId)}/questions`); }
export async function fetchReviewQueue(): Promise<Question[]> { return request('/api/review-queue'); }
export async function fetchEmbeddingStatus(): Promise<unknown> { return request('/api/embeddings/status'); }
export async function healthCheck(): Promise<{ status: string }> { return request('/api/system/health'); }
