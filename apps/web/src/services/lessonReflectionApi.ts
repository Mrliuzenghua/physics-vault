import type { ClassroomReflection } from './classroomReflection';
import { request } from './apiClient.ts';

export async function listLessonReflections(projectId?: string, limit = 100): Promise<ClassroomReflection[]> {
  const params = new URLSearchParams({ limit: String(Math.min(Math.max(limit, 1), 500)) });
  if (projectId) params.set('project_id', projectId);
  const result = await request<{ items: ClassroomReflection[] }>(`/api/lesson-reflections?${params.toString()}`);
  return result.items;
}

export async function saveLessonReflection(
  reflection: ClassroomReflection,
  baseUpdatedAt: string | null = null,
): Promise<ClassroomReflection> {
  const { remoteUpdatedAt: _remoteUpdatedAt, remoteSyncState: _remoteSyncState, ...remoteReflection } = reflection;
  const result = await request<{ reflection: ClassroomReflection }>('/api/lesson-reflections', {
    method: 'POST',
    body: JSON.stringify({ reflection: remoteReflection, base_updated_at: baseUpdatedAt }),
  });
  return result.reflection;
}
