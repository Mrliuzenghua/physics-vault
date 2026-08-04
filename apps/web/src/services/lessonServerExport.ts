import type { ImportPipelineTaskResponse, LessonPackage } from '../types';
import type { LessonExportOptions } from './lessonExport';
import { request } from './apiClient';

export type ServerLessonExportFormat = 'word' | 'pptx';

const ACTIVE_EXPORT_KEY = 'physics-vault.active-export-task.v1';

function sleep(milliseconds: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, milliseconds));
}
function responseFileName(response: Response, fallback: string): string {
  const disposition = response.headers.get('content-disposition') || '';
  const encoded = disposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1];
  if (encoded) {
    try { return decodeURIComponent(encoded); } catch { /* use the quoted fallback */ }
  }
  return disposition.match(/filename="?([^";]+)"?/i)?.[1] || fallback;
}

async function waitForExportTask(initial: ImportPipelineTaskResponse): Promise<ImportPipelineTaskResponse> {
  let task = initial;
  const deadline = Date.now() + 30 * 60 * 1000;
  while (['pending', 'running', 'retrying', 'cancel_requested'].includes(task.status)) {
    if (Date.now() >= deadline) throw new Error('后台导出仍在运行，可稍后到任务中心查看。');
    await sleep(document.hidden ? 8000 : 1600);
    task = await request<ImportPipelineTaskResponse>(`/api/import/tasks/${encodeURIComponent(task.task_id)}`);
  }
  if (task.status !== 'completed') {
    const detail = task.error_info?.message || task.error || (task.status === 'cancelled' ? '导出已取消' : '后台导出失败');
    throw new Error(detail);
  }
  return task;
}

async function downloadExportTask(task: ImportPipelineTaskResponse, format: ServerLessonExportFormat): Promise<void> {
  const response = await fetch(`/api/tasks/${encodeURIComponent(task.task_id)}/download`);
  if (!response.ok) {
    const payload = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(String(payload.detail || `下载失败（HTTP ${response.status}）`));
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = responseFileName(response, format === 'word' ? 'physics-vault.docx' : 'physics-vault.pptx');
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export async function exportLessonOnServer(
  format: ServerLessonExportFormat,
  lessonPackage: LessonPackage,
  options: LessonExportOptions,
): Promise<ImportPipelineTaskResponse> {
  const endpoint = format === 'word' ? '/api/exports/word' : '/api/exports/pptx';
  const submitted = await request<ImportPipelineTaskResponse>(endpoint, {
    method: 'POST',
    body: JSON.stringify({
      lesson_package: lessonPackage,
      include_answers: options.includeAnswers,
      include_analysis: options.includeAnalysis,
      file_name: lessonPackage.title,
    }),
  });
  localStorage.setItem(ACTIVE_EXPORT_KEY, JSON.stringify({ taskId: submitted.task_id, format, createdAt: new Date().toISOString() }));
  try {
    const completed = await waitForExportTask(submitted);
    await downloadExportTask(completed, format);
    return completed;
  } finally {
    localStorage.removeItem(ACTIVE_EXPORT_KEY);
  }
}
