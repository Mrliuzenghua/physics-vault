import type { LessonPackage } from '../types';
import type {
  SavedHandoutDocument,
  SavedHandoutListResponse,
  SavedHandoutSummary,
  SavedHandoutVersion,
  SavedHandoutVersionListResponse,
} from '../types/lessonDocument';
import { ApiError, request } from './apiClient.ts';

export async function saveSavedLessonPackage(
  lessonPackage: LessonPackage,
  sourceWorkbenchId?: string,
): Promise<SavedHandoutDocument> {
  return request<SavedHandoutDocument>('/api/lesson-documents/saved-handouts', {
    method: 'POST',
    body: JSON.stringify({ lesson_package: lessonPackage, source_workbench_id: sourceWorkbenchId }),
  });
}

export async function listSavedHandoutsFromServer(limit = 100): Promise<SavedHandoutSummary[]> {
  const result = await request<SavedHandoutListResponse>(
    `/api/lesson-documents/saved-handouts?limit=${Math.min(Math.max(limit, 1), 100)}`,
  );
  return result.items;
}

export async function fetchSavedHandout(documentId: string): Promise<SavedHandoutDocument | null> {
  try {
    return await request<SavedHandoutDocument>(`/api/lesson-documents/saved-handouts/${encodeURIComponent(documentId)}`);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null;
    throw error;
  }
}

export async function renameSavedHandout(documentId: string, title: string): Promise<SavedHandoutDocument> {
  return request<SavedHandoutDocument>(`/api/lesson-documents/saved-handouts/${encodeURIComponent(documentId)}`, {
    method: 'PATCH',
    body: JSON.stringify({ title }),
  });
}

export async function listSavedHandoutVersions(documentId: string): Promise<SavedHandoutVersion[]> {
  const result = await request<SavedHandoutVersionListResponse>(
    `/api/lesson-documents/saved-handouts/${encodeURIComponent(documentId)}/versions`,
  );
  return result.items;
}

export async function restoreSavedHandoutVersion(
  documentId: string,
  version: number,
): Promise<SavedHandoutDocument> {
  return request<SavedHandoutDocument>(
    `/api/lesson-documents/saved-handouts/${encodeURIComponent(documentId)}/versions/${version}/restore`,
    { method: 'POST' },
  );
}
