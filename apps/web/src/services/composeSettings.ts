import { DEFAULT_CONFIG as DEFAULT_HEADER_FOOTER } from '../components/handout/HandoutHeaderFooterConfigPanel';
import { DEFAULT_STYLE_CONFIG } from '../components/handout/handoutStylePresets';
import type { HandoutHeaderFooterConfig, HandoutStyleConfig } from '../types';
import type { SlideDeckTemplate } from '../types/slides';

const STORAGE_KEY = 'physics-vault.compose-user-settings.v1';

export type ComposeAnswerExportMode = 'end_answer' | 'end_answer_analysis' | 'after_answer' | 'after_answer_analysis';

export interface ComposeUserSettings {
  headerFooter: HandoutHeaderFooterConfig;
  styleConfig: HandoutStyleConfig;
  slideTemplate: SlideDeckTemplate;
  showAnswers: boolean;
  showAnalysis: boolean;
  outputProfile: 'student' | 'teacher';
  answerExportMode: ComposeAnswerExportMode;
  documentZoom: number;
  zoomMode: 'fit-width' | 'manual';
}
const DEFAULT_SETTINGS: ComposeUserSettings = {
  headerFooter: DEFAULT_HEADER_FOOTER,
  styleConfig: DEFAULT_STYLE_CONFIG,
  slideTemplate: 'teach_practice_teach',
  showAnswers: false,
  showAnalysis: false,
  outputProfile: 'student',
  answerExportMode: 'end_answer_analysis',
  documentZoom: 72,
  zoomMode: 'fit-width',
};

export function getComposeUserSettings(): ComposeUserSettings {
  if (typeof window === 'undefined') return DEFAULT_SETTINGS;
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    const stored = raw ? JSON.parse(raw) as Partial<ComposeUserSettings> : {};
    return {
      ...DEFAULT_SETTINGS,
      ...stored,
      headerFooter: { ...DEFAULT_HEADER_FOOTER, ...(stored.headerFooter || {}) },
      styleConfig: { ...DEFAULT_STYLE_CONFIG, ...(stored.styleConfig || {}) },
    };
  } catch {
    return DEFAULT_SETTINGS;
  }
}

export function saveComposeUserSettings(settings: ComposeUserSettings): void {
  if (typeof window === 'undefined') return;
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
  } catch {
    // Ignore storage quota and private-mode failures; the editor remains usable.
  }
}
