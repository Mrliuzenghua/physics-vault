/**
 * LocalStorage-backed persistence for handout style presets.
 *
 * Stored under key: physics-vault.handout-style-presets
 */

import type { HandoutStyleConfig, HandoutStylePreset } from '../../types';
import { isRecord, readJsonStorage, writeJsonStorage } from '../../services/safeStorage.ts';

const STORAGE_KEY = 'physics-vault.handout-style-presets';

// ── Default style config ──────────────────────────────────────────

export const DEFAULT_STYLE_CONFIG: HandoutStyleConfig = {
  fontFamily: 'songti',
  fontSize: 12,
  lineHeight: 1.55,
  paragraphSpacing: 4,
  questionSpacing: 10,
  figureScale: 1,
  pageMarginTop: 12,
  pageMarginBottom: 14,
  pageMarginLeft: 14,
  pageMarginRight: 14,
  questionNumberStyle: 'decimal',
  pageSize: 'A4',
  pageOrientation: 'portrait',
  layoutMode: 'flow',
  optionLayout: 'auto',
  keepQuestionTogether: true,
  keepFigureWithStem: true,
  startLongQuestionOnNewPage: true,
  pageFillPercent: 90,
};

// ── Default presets ───────────────────────────────────────────────

const DEFAULT_PRESETS: HandoutStylePreset[] = [
  {
    id: '__default__',
    name: '标准讲义',
    category: 'handout',
    description: 'A4 流式编辑，自动选项布局与智能分页',
    config: { ...DEFAULT_STYLE_CONFIG },
    createdAt: '2025-01-01T00:00:00Z',
    updatedAt: '2025-01-01T00:00:00Z',
  },
  {
    id: '__compact__',
    name: '紧凑版',
    category: 'exam',
    description: '压缩题间距，适合周练与试卷',
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
      layoutMode: 'flow',
      pageFillPercent: 94,
    },
    createdAt: '2025-01-01T00:00:00Z',
    updatedAt: '2025-01-01T00:00:00Z',
  },
  {
    id: '__large__',
    name: '大字版',
    category: 'large-format',
    description: '大字号与宽松行距，适合课堂展示',
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
      layoutMode: 'flow',
      optionLayout: 'single',
      pageFillPercent: 86,
    },
    createdAt: '2025-01-01T00:00:00Z',
    updatedAt: '2025-01-01T00:00:00Z',
  },
  {
    id: '__teacher__',
    name: '教师讲义',
    category: 'teacher',
    description: '解析阅读优先，长题从新页开始',
    config: {
      ...DEFAULT_STYLE_CONFIG,
      fontSize: 13,
      lineHeight: 1.7,
      questionSpacing: 16,
      optionLayout: 'single',
      pageFillPercent: 84,
    },
    createdAt: '2025-01-01T00:00:00Z',
    updatedAt: '2025-01-01T00:00:00Z',
  },
  {
    id: '__a3_double__',
    name: 'A3 双栏试卷',
    category: 'exam',
    description: 'A3 横向双栏，适合正式试卷输出',
    config: {
      ...DEFAULT_STYLE_CONFIG,
      pageSize: 'A3',
      pageOrientation: 'landscape',
      layoutMode: 'paged-double',
      fontSize: 12,
      lineHeight: 1.5,
      optionLayout: 'auto',
      pageFillPercent: 93,
      pageMarginLeft: 16,
      pageMarginRight: 16,
    },
    createdAt: '2025-01-01T00:00:00Z',
    updatedAt: '2025-01-01T00:00:00Z',
  },
];

// ── Public API ─────────────────────────────────────────────────────

export function loadPresets(): HandoutStylePreset[] {
  const parsed = readJsonStorage<unknown>(STORAGE_KEY, []);
  if (!Array.isArray(parsed)) return mergeDefaults([]);
  const valid = parsed.filter((item): item is HandoutStylePreset => (
    isRecord(item)
    && typeof item.id === 'string'
    && typeof item.name === 'string'
    && typeof item.createdAt === 'string'
    && typeof item.updatedAt === 'string'
    && isRecord(item.config)
  ));
  return mergeDefaults(valid);
}

export function savePresets(presets: HandoutStylePreset[]): void {
  // Don't persist built-in defaults — they're always merged at load time
  const userPresets = presets.filter((p) => !p.id.startsWith('__'));
  writeJsonStorage(STORAGE_KEY, userPresets);
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
