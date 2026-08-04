import type { ImportPipelineTaskResponse, LessonPackage } from '../types';
import type { LessonExportOptions } from './lessonExport';
import { request, requestResponse } from './apiClient';
import { downloadResponse } from './fileDownload';

export type ServerLessonExportFormat = 'word' | 'pptx';

const ACTIVE_EXPORT_KEY = 'physics-vault.active-export-task.v1';

function sleep(milliseconds: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, milliseconds));
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
  const response = await requestResponse(`/api/tasks/${encodeURIComponent(task.task_id)}/download`);
  await downloadResponse(response, format === 'word' ? 'physics-vault.docx' : 'physics-vault.pptx');
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
