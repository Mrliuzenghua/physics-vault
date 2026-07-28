/**
 * LocalStorage-backed persistence for handout style presets.
 *
 * Stored under key: physics-vault.handout-style-presets
 */

import type { HandoutStyleConfig, HandoutStylePreset } from '../../types';

const STORAGE_KEY = 'physics-vault.handout-style-presets';

// ── Default style config ──────────────────────────────────────────

export const DEFAULT_STYLE_CONFIG: HandoutStyleConfig = {
  fontFamily: 'songti',
  fontSize: 14,
  lineHeight: 1.9,
  paragraphSpacing: 6,
  questionSpacing: 18,
  figureScale: 1,
  pageMarginTop: 15,
  pageMarginBottom: 20,
  pageMarginLeft: 18,
  pageMarginRight: 18,
  questionNumberStyle: 'decimal',
  pageSize: 'A4',
  pageOrientation: 'portrait',
  layoutMode: 'paged-single',
};

// ── Default presets ───────────────────────────────────────────────

const DEFAULT_PRESETS: HandoutStylePreset[] = [
  {
    id: '__default__',
    name: '标准讲义',
    config: { ...DEFAULT_STYLE_CONFIG },
    createdAt: '2025-01-01T00:00:00Z',
    updatedAt: '2025-01-01T00:00:00Z',
  },
  {
    id: '__compact__',
    name: '紧凑版',
    config: {
      ...DEFAULT_STYLE_CONFIG,
      fontSize: 12,
      lineHeight: 1.5,
      questionSpacing: 10,
      pageMarginTop: 10,
      pageMarginBottom: 12,
      pageMarginLeft: 14,
      pageMarginRight: 14,
      questionNumberStyle: 'bracket',
      pageSize: 'A4',
      pageOrientation: 'portrait',
      layoutMode: 'paged-double',
    },
    createdAt: '2025-01-01T00:00:00Z',
    updatedAt: '2025-01-01T00:00:00Z',
  },
  {
    id: '__large__',
    name: '大字版',
    config: {
      ...DEFAULT_STYLE_CONFIG,
      fontSize: 18,
      lineHeight: 2.2,
      questionSpacing: 26,
      pageMarginTop: 20,
      pageMarginBottom: 25,
      pageMarginLeft: 22,
      pageMarginRight: 22,
      questionNumberStyle: 'circled',
      pageSize: 'A3',
      pageOrientation: 'portrait',
      layoutMode: 'paged-single',
    },
    createdAt: '2025-01-01T00:00:00Z',
    updatedAt: '2025-01-01T00:00:00Z',
  },
];

// ── Public API ─────────────────────────────────────────────────────

export function loadPresets(): HandoutStylePreset[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return mergeDefaults([]);
    const parsed: HandoutStylePreset[] = JSON.parse(raw);
    if (!Array.isArray(parsed)) return mergeDefaults([]);
    return mergeDefaults(parsed);
  } catch {
    return mergeDefaults([]);
  }
}

export function savePresets(presets: HandoutStylePreset[]): void {
  // Don't persist built-in defaults — they're always merged at load time
  const userPresets = presets.filter((p) => !p.id.startsWith('__'));
  localStorage.setItem(STORAGE_KEY, JSON.stringify(userPresets));
}

export function savePreset(preset: HandoutStylePreset): HandoutStylePreset[] {
  const all = loadPresets();
  const idx = all.findIndex((p) => p.id === preset.id);
  const now = new Date().toISOString();
  const saved: HandoutStylePreset = {
    ...preset,
    updatedAt: now,
    createdAt: idx >= 0 ? all[idx].createdAt : now,
  };
  if (idx >= 0) {
    all[idx] = saved;
  } else {
    all.push(saved);
  }
  savePresets(all);
  return loadPresets();
}

export function deletePreset(id: string): HandoutStylePreset[] {
  // Don't allow deleting built-in defaults
  if (id.startsWith('__')) return loadPresets();
  const all = loadPresets().filter((p) => p.id !== id);
  savePresets(all);
  return loadPresets();
}

export function makePresetId(): string {
  return `preset-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`;
}

// ── Internal ───────────────────────────────────────────────────────

function mergeDefaults(userPresets: HandoutStylePreset[]): HandoutStylePreset[] {
  const merged = [...DEFAULT_PRESETS];
  for (const up of userPresets) {
    const normalized = {
      ...up,
      config: {
        ...DEFAULT_STYLE_CONFIG,
        ...up.config,
      },
    };
    const idx = merged.findIndex((dp) => dp.id === up.id);
    if (idx >= 0) {
      merged[idx] = normalized;
    } else {
      merged.push(normalized);
    }
  }
  return merged;
}
