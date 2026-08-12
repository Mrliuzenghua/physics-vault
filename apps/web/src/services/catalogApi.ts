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

export interface KnowledgeSuggestion {
  topic3_id: string;
  topic3_name: string;
  topic2_id: string;
  topic2_name: string;
  topic1_id: string;
  topic1_name: string;
  score: number;
  confidence: string;
  rationale: string;
  evidence_source?: 'prompt' | 'options' | 'figure' | 'analysis' | 'none';
}

export interface MissingKnowledgeDiagnosisItem {
  question_id: string;
  title_preview: string;
  status: string;
  suggestions: KnowledgeSuggestion[];
  recommended_topic3_ids: string[];
  auto_fix_safe: boolean;
  content_quality?: {
    status: 'ok' | 'content_fragment' | 'suspected_cross_subject';
    semantic_char_count: number;
    has_option_evidence: boolean;
    has_figure_text_evidence: boolean;
    requires_image_review: boolean;
    issues: string[];
    message: string;
  };
  auto_fix_evidence: {
    top_score: number;
    second_score: number;
    score_margin: number;
    direct_match_in_title_or_stem: boolean;
  };
  reason: string;
}

export interface MissingKnowledgeDiagnosisResponse {
  items: MissingKnowledgeDiagnosisItem[];
  total: number;
  limit: number;
  offset: number;
  summary: Record<string, number>;
}

export async function fetchDatabaseStatus(): Promise<DatabaseStatus> { return request('/api/system/db-status'); }
export async function fetchCatalogHealth(): Promise<CatalogHealthReport> { return request('/api/system/catalog-health'); }
export async function fetchMissingKnowledgeDiagnosis(limit = 20, offset = 0): Promise<MissingKnowledgeDiagnosisResponse> {
  return request(`/api/system/catalog-health/missing-knowledge?limit=${limit}&offset=${offset}`);
}
export async function fetchImages(params: Record<string, string>): Promise<unknown[]> { return request(`/api/images?${new URLSearchParams(params)}`); }
export async function fetchPapers(): Promise<unknown[]> { return request('/api/papers'); }
export async function fetchPaperQuestions(paperId: string): Promise<Question[]> { return request(`/api/papers/${encodeURIComponent(paperId)}/questions`); }
export async function fetchReviewQueue(): Promise<Question[]> { return request('/api/review-queue'); }
export async function fetchEmbeddingStatus(): Promise<unknown> { return request('/api/embeddings/status'); }
export async function healthCheck(): Promise<{ status: string }> { return request('/api/system/health'); }
