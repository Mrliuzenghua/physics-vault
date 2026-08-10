import type { QuestionAnnotation } from '../types';
import { request } from './apiClient.ts';

export async function fetchAnnotations(questionId: string): Promise<QuestionAnnotation[]> {
  return request(`/api/questions/${encodeURIComponent(questionId)}/annotations`);
}

export async function createAnnotation(
  questionId: string,
  body: Partial<QuestionAnnotation>,
): Promise<QuestionAnnotation> {
  return request(`/api/questions/${encodeURIComponent(questionId)}/annotations`, {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export async function updateAnnotation(
  annotationId: string,
  patch: Partial<QuestionAnnotation>,
): Promise<QuestionAnnotation> {
  return request(`/api/questions/annotations/${encodeURIComponent(annotationId)}`, {
    method: 'PUT',
    body: JSON.stringify(patch),
  });
}

export async function deleteAnnotation(annotationId: string): Promise<{ status: string; annotation_id: string }> {
  return request(`/api/questions/annotations/${encodeURIComponent(annotationId)}`, { method: 'DELETE' });
}
