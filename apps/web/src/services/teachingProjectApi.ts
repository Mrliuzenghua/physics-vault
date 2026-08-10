import type { TeachingProject, TeachingProjectSummary } from '../types/teachingProject';
import { ApiError, request } from './apiClient.ts';

function boundedLimit(limit: number): number {
  return Math.min(Math.max(limit, 1), 200);
}

export async function listTeachingProjects(limit = 100): Promise<TeachingProjectSummary[]> {
  const result = await request<{ items: TeachingProjectSummary[] }>(
    `/api/teaching-projects?limit=${boundedLimit(limit)}`,
  );
  return result.items;
}

export async function fetchTeachingProject(projectId: string): Promise<TeachingProject | null> {
  try {
    return await request<TeachingProject>(`/api/teaching-projects/${encodeURIComponent(projectId)}`);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null;
    throw error;
  }
}

export async function saveTeachingProjectSnapshot(
  project: TeachingProject,
  baseUpdatedAt: string | null = null,
): Promise<TeachingProject> {
  return request<TeachingProject>('/api/teaching-projects', {
    method: 'POST',
    body: JSON.stringify({ project, base_updated_at: baseUpdatedAt }),
  });
}

export async function archiveTeachingProject(
  projectId: string,
  baseUpdatedAt: string | null = null,
): Promise<TeachingProject> {
  return request<TeachingProject>(`/api/teaching-projects/${encodeURIComponent(projectId)}/archive`, {
    method: 'POST',
    body: JSON.stringify({ base_updated_at: baseUpdatedAt }),
  });
}

export async function duplicateTeachingProject(projectId: string, title?: string): Promise<TeachingProject> {
  return request<TeachingProject>(`/api/teaching-projects/${encodeURIComponent(projectId)}/duplicate`, {
    method: 'POST',
    body: JSON.stringify({ title: title || null }),
  });
}
