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
