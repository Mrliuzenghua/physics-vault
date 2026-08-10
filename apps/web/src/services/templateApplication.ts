import type {
  HandoutHeaderFooterConfig,
  HandoutStyleConfig,
  TemplateConfig,
} from '../types';
import { DEFAULT_STYLE_CONFIG } from '../components/handout/handoutStylePresets';

export type TemplateApplyMode = 'fill' | 'overwrite';

export interface TemplateConfigChange {
  key: keyof TemplateConfig;
  before: string;
  after: string;
}

const TEMPLATE_KEYS: Array<keyof TemplateConfig> = [
  'knowledge_mode', 'knowledge_style', 'knowledge_length', 'show_answer', 'show_analysis',
  'question_number_style', 'figure_scale', 'font_family', 'font_size', 'line_height',
  'page_size', 'orientation', 'header', 'footer', 'option_layout', 'keep_question_together',
  'keep_figure_with_stem', 'start_long_question_on_new_page', 'page_fill_percent',
];

export function describeTemplateChanges(current: TemplateConfig, template: TemplateConfig): TemplateConfigChange[] {
  return TEMPLATE_KEYS.flatMap((key) => {
    const before = current[key];
    const after = template[key];
    if (after === undefined || String(before ?? '') === String(after ?? '')) return [];
    return [{ key, before: String(before ?? '未设置'), after: String(after) }];
  });
}

function clamp(value: number, minimum: number, maximum: number): number {
  return Math.max(minimum, Math.min(maximum, value));
}

function resolveFontFamily(value?: string): HandoutStyleConfig['fontFamily'] {
  const font = String(value || '').toLowerCase();
  if (font.includes('simhei') || font.includes('黑体') || font.includes('sans')) return 'heiti';
  if (font.includes('kaiti') || font.includes('楷体')) return 'kaiti';
  if (font.includes('fangsong') || font.includes('仿宋')) return 'fangsong';
  if (font.includes('system') || font.includes('yahei')) return 'system';
  return 'songti';
}

export function applyTemplateToStyleConfig(
  current: HandoutStyleConfig,
  template: TemplateConfig,
  mode: TemplateApplyMode = 'overwrite',
): HandoutStyleConfig {
  const parsedFontSize = Number.parseFloat(template.font_size || '');
  const parsedLineHeight = Number.parseFloat(template.line_height || '');
  const parsedFigureScale = Number.parseFloat(template.figure_scale || '');
  const pageSize = template.page_size || current.pageSize;
  const pageOrientation = template.orientation || current.pageOrientation;
  const numberStyle = template.question_number_style === 'circled'
    ? 'circled'
    : template.question_number_style === 'paren'
      ? 'bracket'
      : 'decimal';

  const next: HandoutStyleConfig = {
    ...current,
    fontFamily: resolveFontFamily(template.font_family),
    fontSize: Number.isFinite(parsedFontSize) ? clamp(parsedFontSize, 10, 20) : current.fontSize,
    lineHeight: Number.isFinite(parsedLineHeight) ? clamp(parsedLineHeight, 1.3, 2) : current.lineHeight,
    figureScale: Number.isFinite(parsedFigureScale) ? clamp(parsedFigureScale, 0.45, 1) : current.figureScale,
    questionNumberStyle: numberStyle,
    pageSize,
    pageOrientation,
    layoutMode: pageSize === 'A3' || pageOrientation === 'landscape' ? 'paged-double' : 'paged-single',
    optionLayout: template.option_layout || current.optionLayout,
    keepQuestionTogether: template.keep_question_together ?? current.keepQuestionTogether,
    keepFigureWithStem: template.keep_figure_with_stem ?? current.keepFigureWithStem,
    startLongQuestionOnNewPage: template.start_long_question_on_new_page ?? current.startLongQuestionOnNewPage,
    pageFillPercent: Number.isFinite(template.page_fill_percent)
      ? clamp(Number(template.page_fill_percent), 78, 98)
      : current.pageFillPercent,
  };
  if (mode === 'overwrite') return next;
  const defaultConfig = DEFAULT_STYLE_CONFIG;
  const result = { ...next };
  (Object.keys(defaultConfig) as Array<keyof HandoutStyleConfig>).forEach((key) => {
    if (current[key] !== undefined && current[key] !== defaultConfig[key]) result[key] = current[key] as never;
  });
  return result;
}

export function applyTemplateToHeaderFooter(
  current: HandoutHeaderFooterConfig,
  template: TemplateConfig,
  mode: TemplateApplyMode = 'overwrite',
): HandoutHeaderFooterConfig {
  const headerText = template.header?.trim() || '';
  const footerText = template.footer?.trim() || '';
  const next = {
    ...current,
    headerEnabled: Boolean(headerText),
    headerText,
    footerEnabled: Boolean(footerText),
    footerText,
  };
  if (mode === 'overwrite') return next;
  const defaults: HandoutHeaderFooterConfig = {
    headerEnabled: false,
    headerText: '',
    headerAlign: 'left',
    footerEnabled: false,
    footerText: '',
    footerAlign: 'left',
    showPageNumber: false,
  };
  return {
    ...next,
    headerEnabled: current.headerEnabled !== defaults.headerEnabled ? current.headerEnabled : next.headerEnabled,
    headerText: current.headerText || next.headerText,
    headerAlign: current.headerText ? current.headerAlign : next.headerAlign,
    footerEnabled: current.footerEnabled !== defaults.footerEnabled ? current.footerEnabled : next.footerEnabled,
    footerText: current.footerText || next.footerText,
    footerAlign: current.footerText ? current.footerAlign : next.footerAlign,
    showPageNumber: current.showPageNumber !== defaults.showPageNumber ? current.showPageNumber : next.showPageNumber,
  };
}
