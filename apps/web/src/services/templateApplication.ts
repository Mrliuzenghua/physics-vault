import type {
  HandoutHeaderFooterConfig,
  HandoutStyleConfig,
  TemplateConfig,
} from '../types';

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

  return {
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
}

export function applyTemplateToHeaderFooter(
  current: HandoutHeaderFooterConfig,
  template: TemplateConfig,
): HandoutHeaderFooterConfig {
  const headerText = template.header?.trim() || '';
  const footerText = template.footer?.trim() || '';
  return {
    ...current,
    headerEnabled: Boolean(headerText),
    headerText,
    footerEnabled: Boolean(footerText),
    footerText,
  };
}
