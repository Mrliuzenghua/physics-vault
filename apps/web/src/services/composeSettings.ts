import { DEFAULT_CONFIG as DEFAULT_HEADER_FOOTER } from '../components/handout/HandoutHeaderFooterConfigPanel';
import { DEFAULT_STYLE_CONFIG } from '../components/handout/handoutStylePresets';
import type { HandoutHeaderFooterConfig, HandoutStyleConfig } from '../types';
import type { SlideDeckTemplate } from '../types/slides';
import { isRecord, readJsonStorage, writeJsonStorage } from './safeStorage.ts';

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
  const stored = readJsonStorage<Record<string, unknown>>(STORAGE_KEY, {}, isRecord);
  const headerFooter = isRecord(stored.headerFooter) ? stored.headerFooter : {};
  const styleConfig = isRecord(stored.styleConfig) ? stored.styleConfig : {};
  const slideTemplate = ['teach_practice_teach', 'teach_then_practice', 'practice_only'].includes(String(stored.slideTemplate))
    ? stored.slideTemplate as SlideDeckTemplate
    : DEFAULT_SETTINGS.slideTemplate;
  const answerExportMode = ['end_answer', 'end_answer_analysis', 'after_answer', 'after_answer_analysis'].includes(String(stored.answerExportMode))
    ? stored.answerExportMode as ComposeAnswerExportMode
    : DEFAULT_SETTINGS.answerExportMode;
  const documentZoom = Number(stored.documentZoom);
  return {
    headerFooter: { ...DEFAULT_HEADER_FOOTER, ...headerFooter },
    styleConfig: { ...DEFAULT_STYLE_CONFIG, ...styleConfig },
    slideTemplate,
    showAnswers: typeof stored.showAnswers === 'boolean' ? stored.showAnswers : DEFAULT_SETTINGS.showAnswers,
    showAnalysis: typeof stored.showAnalysis === 'boolean' ? stored.showAnalysis : DEFAULT_SETTINGS.showAnalysis,
    outputProfile: stored.outputProfile === 'teacher' ? 'teacher' : 'student',
    answerExportMode,
    documentZoom: Number.isFinite(documentZoom) ? Math.max(50, Math.min(125, documentZoom)) : DEFAULT_SETTINGS.documentZoom,
    zoomMode: stored.zoomMode === 'manual' ? 'manual' : 'fit-width',
  };
}

export function saveComposeUserSettings(settings: ComposeUserSettings): void {
  writeJsonStorage(STORAGE_KEY, settings);
}
