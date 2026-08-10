import type {
  TaskActionResponse,
  TaskCenterItem,
  TaskCenterListResponse,
  TaskContextResponse,
  TaskStageEvent,
  TaskLog,
} from '../types';
import { request, requestResponse } from './apiClient';
import { downloadResponse } from './fileDownload';

export interface TaskFilters {
  status?: string;
  task_type?: string;
  created_from?: string;
  created_to?: string;
  page?: number;
  page_size?: number;
}

export async function fetchProcessingRuns(): Promise<TaskLog[]> {
  return request('/processing-runs');
}

export async function fetchTasks(params: TaskFilters = {}): Promise<TaskCenterListResponse> {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== '') search.set(key, String(value));
  });
  return request(`/api/tasks?${search.toString()}`);
}

export async function fetchTask(taskId: string): Promise<TaskCenterItem> {
  return request(`/api/tasks/${encodeURIComponent(taskId)}`);
}

export async function fetchTaskStageEvents(taskId: string): Promise<TaskStageEvent[]> {
  return request(`/api/tasks/${encodeURIComponent(taskId)}/events`);
}

export async function fetchTaskContext(taskId: string): Promise<TaskContextResponse> {
  return request(`/api/tasks/${encodeURIComponent(taskId)}/context`);
}

export async function retryTask(taskId: string): Promise<TaskActionResponse> {
  return request(`/api/tasks/${encodeURIComponent(taskId)}/retry`, { method: 'POST' });
}

export async function cancelTask(taskId: string): Promise<TaskActionResponse> {
  return request(`/api/tasks/${encodeURIComponent(taskId)}/cancel`, { method: 'POST' });
}

export async function downloadTaskResult(taskId: string): Promise<void> {
  const response = await requestResponse(`/api/tasks/${encodeURIComponent(taskId)}/download`);
  await downloadResponse(response, `task-${taskId}`);
}
