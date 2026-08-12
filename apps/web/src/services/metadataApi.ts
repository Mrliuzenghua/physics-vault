import type {
  BatchMetadataRequest,
  BatchMetadataResponse,
  KnowledgePoint,
  KnowledgePointFlatItem,
} from '../types';
import { request } from './apiClient.ts';

export async function batchUpdateMetadata(body: BatchMetadataRequest): Promise<BatchMetadataResponse> {
  return request('/api/questions/batch-metadata', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export async function generateKnowledge(
  body: {
    knowledge_points: string[];
    style?: string;
    length?: string;
    include_formula?: boolean;
    include_common_mistakes?: boolean;
    force_regenerate?: boolean;
  },
): Promise<{
  knowledge_key: string;
  title: string;
  content: string;
  outline: string[];
  generated: boolean;
  from_cache: boolean;
  warnings: string[];
}> {
  return request('/api/ai/knowledge/generate', { method: 'POST', body: JSON.stringify(body) });
}

export async function fetchQuestionKnowledgePoints(id: string): Promise<KnowledgePoint[]> {
  return request(`/questions/${encodeURIComponent(id)}/knowledge-points`);
}

export async function updateQuestionKnowledgePoints(id: string, points: KnowledgePoint[]): Promise<void> {
  await request(`/questions/${encodeURIComponent(id)}/knowledge-points`, {
    method: 'PUT',
    body: JSON.stringify(points),
  });
}

export async function fetchKnowledgePoints(): Promise<KnowledgePointFlatItem[]> {
  return request('/knowledge-points');
}

export async function fetchKnowledgePointCounts(): Promise<Record<string, number>> {
  return request('/knowledge-points/counts');
}

export interface KnowledgeReplacementPreview {
  question_id: string;
  before_links: KnowledgePoint[];
  replacement_items: Array<{
    rank: number;
    topic3_id: string;
    source: string;
    confidence: number;
    note?: string | null;
  }>;
  changed: boolean;
  requires_confirmation: boolean;
  operation_plan?: { operation_id: string } | null;
}

export interface KnowledgeReplacementExecution {
  operation_id: string;
  status: string;
  result?: { question_id: string; links: KnowledgePoint[]; audit_batch_id?: string | null } | null;
  error?: string | null;
  idempotent: boolean;
}

export async function previewQuestionKnowledgeReplacement(
  questionId: string,
  topic3Id: string,
  confidence: number,
): Promise<KnowledgeReplacementPreview> {
  return request(`/api/questions/${encodeURIComponent(questionId)}/knowledge-points/preview-replace`, {
    method: 'POST',
    body: JSON.stringify({
      items: [{ rank: 1, topic3_id: topic3Id, source: 'manual_review', confidence, note: '教师在知识目录维护页确认' }],
      reason: '教师确认未归类题的知识目录',
    }),
  });
}

export async function confirmQuestionKnowledgeReplacement(operationId: string): Promise<KnowledgeReplacementExecution> {
  return request('/api/questions/knowledge-points/confirm-operation', {
    method: 'POST',
    body: JSON.stringify({ operation_id: operationId }),
  });
}
