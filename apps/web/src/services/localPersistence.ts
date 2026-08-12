import type { FileTaskState, StoredTaskState, Template } from '../types';
import { isRecord, readJsonStorage, removeStorageValue, writeJsonStorage } from './safeStorage.ts';

const IMPORT_TASKS_KEY = 'physics-vault.import.tasks';
const MAX_RESULT_TEXT_LEN = 500;
const CONVERT_RESULT_KEYS = ['output_path', 'source_path', 'target_format'];
const CLEAN_RESULT_KEYS = ['original_length', 'cleaned_length'];
const PARSE_RESULT_KEYS = ['question_count'];
const AI_PARSE_RESULT_KEYS = ['question_count', 'document_type', 'page_count'];

function toStoredTasks(tasks: FileTaskState[]): StoredTaskState[] {
  return tasks.map((task) => {
    const now = new Date().toISOString();
    return {
      fileId: task.fileId,
      fileName: task.fileName,
      status: task.status,
      currentStep: task.currentStep,
      convertTask: toStoredRef(task.convertTask, CONVERT_RESULT_KEYS),
      cleanTask: toStoredRef(task.cleanTask, CLEAN_RESULT_KEYS),
      parseTask: toStoredRef(task.parseTask, PARSE_RESULT_KEYS),
      aiParseTask: toStoredRef(task.aiParseTask, AI_PARSE_RESULT_KEYS),
      error: task.error,
      taskSourceType: task.taskSourceType,
      savedAt: now,
    };
  });
}

function toStoredRef(
  task: FileTaskState['convertTask'],
  summaryKeys: string[],
): StoredTaskState['convertTask'] {
  if (!task) return null;
  const summary: Record<string, unknown> = {};
  if (task.result) {
    for (const key of summaryKeys) {
      const val = task.result[key];
      if (val != null) {
        summary[key] =
          typeof val === 'string' && val.length > MAX_RESULT_TEXT_LEN
            ? `${val.slice(0, MAX_RESULT_TEXT_LEN)}...`
            : val;
      }
    }

    if (typeof task.result.cleaned_text === 'string') {
      const text = task.result.cleaned_text;
      summary.cleaned_text_preview =
        text.length > MAX_RESULT_TEXT_LEN ? `${text.slice(0, MAX_RESULT_TEXT_LEN)}...` : text;
    }
  }

  return {
    task_id: task.task_id,
    task_type: task.task_type,
    status: task.status,
    error: task.error,
    resultSummary: Object.keys(summary).length > 0 ? summary : null,
  };
}

export function loadPersistedImportTasks(): StoredTaskState[] {
  const parsed = readJsonStorage<unknown>(IMPORT_TASKS_KEY, []);
  return Array.isArray(parsed)
    ? parsed.filter((item): item is StoredTaskState => (
        isRecord(item)
        && typeof item.fileId === 'string'
        && typeof item.fileName === 'string'
        && ['pending', 'running', 'completed', 'failed'].includes(String(item.status))
        && ['convert', 'clean', 'parse', 'ai_parse', 'done'].includes(String(item.currentStep))
        && typeof item.savedAt === 'string'
      ))
    : [];
}

export function savePersistedImportTasks(tasks: FileTaskState[]): void {
  writeJsonStorage(IMPORT_TASKS_KEY, toStoredTasks(tasks));
}

export function clearPersistedImportTasks(): void {
  removeStorageValue(IMPORT_TASKS_KEY);
}

const TEMPLATES_KEY = 'physics-vault.templates';

export function loadTemplates(): Template[] {
  const parsed = readJsonStorage<unknown>(TEMPLATES_KEY, []);
  return Array.isArray(parsed)
    ? parsed.filter((item): item is Template => (
        isRecord(item)
        && typeof item.id === 'string'
        && typeof item.name === 'string'
        && ['style', 'layout', 'handout', 'teaching'].includes(String(item.type))
        && isRecord(item.config)
      ))
    : [];
}

export function saveTemplate(template: Template): Template[] {
  const existing = loadTemplates();
  const idx = existing.findIndex((item) => item.id === template.id);
  const now = new Date().toISOString();
  if (idx >= 0) {
    existing[idx] = { ...template, updated_at: now };
  } else {
    existing.push({ ...template, created_at: template.created_at || now, updated_at: now });
  }
  writeJsonStorage(TEMPLATES_KEY, existing);
  return existing;
}

export function deleteTemplate(templateId: string): Template[] {
  const existing = loadTemplates();
  const filtered = existing.filter((item) => item.id !== templateId);
  writeJsonStorage(TEMPLATES_KEY, filtered);
  return filtered;
}

const MATERIAL_PACKAGES_KEY = 'physics-vault.material-packages';

export function loadMaterialPackages(): import('../types').TemplateMaterialPackage[] {
  const parsed = readJsonStorage<unknown>(MATERIAL_PACKAGES_KEY, []);
  return Array.isArray(parsed)
    ? parsed.filter((item): item is import('../types').TemplateMaterialPackage => (
        isRecord(item)
        && typeof item.id === 'string'
        && typeof item.name === 'string'
        && Array.isArray(item.questions)
        && Array.isArray(item.questionIds)
        && isRecord(item.config)
      ))
    : [];
}

export function saveMaterialPackage(
  pkg: import('../types').TemplateMaterialPackage,
): import('../types').TemplateMaterialPackage[] {
  const existing = loadMaterialPackages();
  const idx = existing.findIndex((item) => item.id === pkg.id);
  const now = new Date().toISOString();
  if (idx >= 0) {
    existing[idx] = { ...pkg, updated_at: now };
  } else {
    existing.push({ ...pkg, created_at: pkg.created_at || now, updated_at: now });
  }
  writeJsonStorage(MATERIAL_PACKAGES_KEY, existing);
  return existing;
}

export function deleteMaterialPackage(packageId: string): import('../types').TemplateMaterialPackage[] {
  const existing = loadMaterialPackages();
  const filtered = existing.filter((item) => item.id !== packageId);
  writeJsonStorage(MATERIAL_PACKAGES_KEY, filtered);
  return filtered;
}
