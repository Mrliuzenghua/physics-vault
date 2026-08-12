import type { SearchFilters } from '../types';
import { isRecord, readJsonStorage, writeJsonStorage } from './safeStorage.ts';

const SHARE_HISTORY_KEY = 'physics_vault.question_share_history';
const SEARCH_PRESET_KEY = 'physics_vault.question_search_presets';

export interface ShareHistoryItem {
  createdAt: string;
  questionIds: string[];
  text: string;
}

export interface SearchPreset {
  id: string;
  name: string;
  filters: SearchFilters;
}

function isSearchPreset(value: unknown): value is SearchPreset {
  return isRecord(value)
    && typeof value.id === 'string'
    && typeof value.name === 'string'
    && isRecord(value.filters);
}

function isShareHistoryItem(value: unknown): value is ShareHistoryItem {
  return isRecord(value)
    && typeof value.createdAt === 'string'
    && typeof value.text === 'string'
    && Array.isArray(value.questionIds)
    && value.questionIds.every((questionId) => typeof questionId === 'string');
}

export function readSearchPresets(): SearchPreset[] {
  const parsed = readJsonStorage<unknown>(SEARCH_PRESET_KEY, []);
  return Array.isArray(parsed) ? parsed.filter(isSearchPreset).slice(0, 8) : [];
}

export function persistSearchPresets(items: SearchPreset[]): void {
  writeJsonStorage(SEARCH_PRESET_KEY, items.slice(0, 8));
}

export function readShareHistory(): ShareHistoryItem[] {
  const parsed = readJsonStorage<unknown>(SHARE_HISTORY_KEY, []);
  return Array.isArray(parsed) ? parsed.filter(isShareHistoryItem).slice(0, 20) : [];
}

export function saveShareHistory(item: ShareHistoryItem): ShareHistoryItem[] {
  const next = [item, ...readShareHistory()].slice(0, 20);
  writeJsonStorage(SHARE_HISTORY_KEY, next);
  return next;
}
