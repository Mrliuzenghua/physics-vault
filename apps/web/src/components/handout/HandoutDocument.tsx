import type { HandoutConfig, HandoutItem } from '../../types';
import HandoutQuestionBlock from './HandoutQuestionBlock';

interface Props {
  items: HandoutItem[];
  config: HandoutConfig;
}

function buildPrintStyles(config: HandoutConfig) {
  const pageSize = config.styleConfig.pageSize || 'A4';
  const orientation = config.styleConfig.pageOrientation || 'portrait';

  return `
  @page {
    size: ${pageSize} ${orientation};
  }

  @media print {
    html, body {
      background: #fff !important;
      -webkit-print-color-adjust: exact;
      print-color-adjust: exact;
    }

    .handout-screen-only {
      display: none !important;
    }

    .handout-page {
      box-shadow: none !important;
      margin: 0 !important;
      padding: 0 !important;
      page-break-after: always;
      border: none !important;
      border-radius: 0 !important;
    }

    .handout-page:last-child {
      page-break-after: auto;
    }

    .question-block {
      break-inside: avoid;
      page-break-inside: avoid;
    }

    .page-break-marker {
      page-break-before: always;
      break-before: page;
    }
  }

  @media screen {
    .print-only {
      display: none !important;
    }
  }
`;
}

function getPageDimensions(config: HandoutConfig) {
  const pageSize = config.styleConfig.pageSize || 'A4';
  const orientation = config.styleConfig.pageOrientation || 'portrait';

  if (pageSize === 'A3') {
    return orientation === 'landscape'
      ? { width: '420mm', minHeight: '297mm' }
      : { width: '297mm', minHeight: '420mm' };
  }

  return orientation === 'landscape'
    ? { width: '297mm', minHeight: '210mm' }
    : { width: '210mm', minHeight: '297mm' };
}

/** Page header — respects HandoutHeaderFooterConfig. Prints with the document. */
function getFontFamilyValue(fontFamily = 'songti') {
  const map = {
    songti: '"Noto Serif SC", "Songti SC", SimSun, serif',
    heiti: '"Noto Sans SC", "Microsoft YaHei", SimHei, sans-serif',
    kaiti: 'KaiTi, "Kaiti SC", serif',
    fangsong: 'FangSong, STFangsong, serif',
    system: '"Microsoft YaHei", Arial, sans-serif',
  };

  return map[fontFamily as keyof typeof map] || map.songti;
}

function getDocumentFontFamily(config: HandoutConfig) {
  return getFontFamilyValue(config.styleConfig.fontFamily);
}

function PageHeader({ config }: { config: HandoutConfig }) {
  const hf = config.headerFooter;
  if (!hf?.headerEnabled || !hf.headerText?.trim()) return null;

  return (
    <div
      style={{
        textAlign: hf.headerAlign,
        marginBottom: 14,
        paddingBottom: 6,
        borderBottom: '1px solid var(--color-border-strong, #cfd6e4)',
        fontSize: 12.5,
        fontWeight: 600,
        letterSpacing: '0.02em',
        color: 'var(--color-text-secondary, #5a6172)',
      }}
    >
      {hf.headerText}
    </div>
  );
}

/** Page footer — respects HandoutHeaderFooterConfig + page number. */
function PageFooter({ config, pageNum }: { config: HandoutConfig; pageNum: number }) {
  const hf = config.headerFooter;
  if (!hf?.footerEnabled && !hf?.showPageNumber) return null;

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent:
          hf.footerEnabled && hf.showPageNumber
            ? 'space-between'
            : hf.footerAlign,
        borderTop: '1px solid var(--color-border, #e3e7ee)',
        paddingTop: 8,
        marginTop: 16,
        fontSize: 11,
        color: 'var(--color-text-muted, #9aa1b3)',
      }}
    >
      {hf.footerEnabled && (
        <span style={{ flex: hf.showPageNumber ? undefined : 1, textAlign: hf.footerAlign }}>
          {hf.footerText || ' '}
        </span>
      )}
      {hf.showPageNumber && (
        <span style={{ flex: hf.footerEnabled ? undefined : 1, textAlign: hf.footerEnabled ? 'right' : hf.footerAlign }}>
          第 {pageNum} 页
        </span>
      )}
    </div>
  );
}

function KnowledgeBlock({ item }: { item: HandoutItem }) {
  return (
    <div
      className="question-block"
      style={{
        breakInside: 'avoid',
        pageBreakInside: 'avoid',
        marginBottom: 20,
        padding: '2px 0 12px',
        borderBottom: '1px solid #d8dee8',
      }}
    >
      <div style={{ marginBottom: 10, display: 'flex', alignItems: 'center', gap: 8 }}>
        <span
          style={{
            color: '#2563eb',
            fontSize: 12,
            fontWeight: 700,
          }}
        >
          知识点
        </span>
        <span style={{ fontSize: 18, fontWeight: 700, color: '#0f172a' }}>{item.title || '核心知识'}</span>
      </div>
      {item.summary && (
        <div style={{ marginBottom: 10, fontSize: 13, lineHeight: 1.8, color: '#475569' }}>
          {item.summary}
        </div>
      )}
      <div style={{ display: 'grid', gap: 8 }}>
        {(item.points || []).map((point, index) => (
          <div
            key={`${item.title}-${index}`}
            style={{
              display: 'flex',
              alignItems: 'flex-start',
              gap: 8,
              fontSize: 14,
              lineHeight: 1.8,
              color: '#1e293b',
            }}
          >
            <span style={{ color: '#2563eb', fontWeight: 700 }}>•</span>
            <span>{point}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function TextBlock({ item, config }: { item: HandoutItem; config: HandoutConfig }) {
  const localStyle = item.style || {};
  const blockFontFamily = localStyle.fontFamily ? getFontFamilyValue(localStyle.fontFamily) : undefined;
  if (item.blockKind === 'exam_title') {
    return (
      <div className="question-block" style={{ marginBottom: 18, breakInside: 'avoid', pageBreakInside: 'avoid' }}>
        <div
          style={{
            whiteSpace: 'pre-wrap',
            fontSize: localStyle.fontSize || 22,
            lineHeight: 1.7,
            fontWeight: localStyle.fontWeight || 700,
            color: '#0f172a',
            fontFamily: blockFontFamily,
            textAlign: localStyle.textAlign || 'center',
          }}
        >
          {item.content || ''}
        </div>
      </div>
    );
  }

  if (item.blockKind === 'name_line') {
    return (
      <div
        className="question-block"
        style={{
          marginBottom: 18,
          padding: '8px 0',
          borderTop: '1px solid #cbd5e1',
          borderBottom: '1px solid #cbd5e1',
          textAlign: localStyle.textAlign || 'center',
          fontSize: localStyle.fontSize || 14,
          lineHeight: 1.8,
          color: '#1f2937',
          breakInside: 'avoid',
          pageBreakInside: 'avoid',
          fontFamily: blockFontFamily,
          fontWeight: localStyle.fontWeight,
        }}
      >
        {item.content || ''}
      </div>
    );
  }

  if (item.blockKind === 'section_title') {
    return (
      <div className="question-block" style={{ marginBottom: 12, paddingTop: 4, breakInside: 'avoid', pageBreakInside: 'avoid' }}>
        <div
          style={{
            fontSize: localStyle.fontSize || 16,
            fontWeight: localStyle.fontWeight || 700,
            lineHeight: 1.8,
            color: '#0f172a',
            fontFamily: blockFontFamily,
            textAlign: localStyle.textAlign || 'left',
          }}
        >
          {item.content || ''}
        </div>
      </div>
    );
  }

  return (
    <div
      className="question-block"
      style={{
        breakInside: 'avoid',
        pageBreakInside: 'avoid',
        marginBottom: 18,
        padding: '0 0 10px',
      }}
    >
      <div style={{ marginBottom: 8, fontSize: 17, fontWeight: 700, color: '#0f172a' }}>
        {item.title || '文本说明'}
      </div>
      <div
        style={{
          whiteSpace: 'pre-wrap',
          fontSize: localStyle.fontSize || config.styleConfig.fontSize,
          lineHeight: 1.9,
          color: '#475569',
          fontFamily: blockFontFamily,
          fontWeight: localStyle.fontWeight,
          textAlign: localStyle.textAlign,
        }}
      >
        {item.content || ''}
      </div>
    </div>
  );
}

export default function HandoutDocument({ items, config }: Props) {
  if (!items || items.length === 0) {
    return (
      <div className="flex h-full items-center justify-center">
        <p className="text-sm" style={{ color: 'var(--color-text-muted)' }}>
          暂无题目
        </p>
      </div>
    );
  }

  // Split items into pages based on page_break markers
  const pages = splitIntoPages(items, config);
  const pageDimensions = getPageDimensions(config);
  const isFlowLayout = config.styleConfig.layoutMode === 'flow';
  const columnCount = config.styleConfig.layoutMode === 'paged-double' ? 2 : 1;
  const documentFontFamily = getDocumentFontFamily(config);

  // Running question number counter across all pages
  let questionNum = 0;

  return (
    <>
      <style>{buildPrintStyles(config)}</style>

      <div className="handout-document" style={{ padding: '24px 0', fontFamily: documentFontFamily }}>
        {pages.map((pageItems, pageIndex) => (
          <div
            key={pageIndex}
            className="handout-page"
            style={{
              width: pageDimensions.width,
              minHeight: isFlowLayout ? 'auto' : pageDimensions.minHeight,
              margin: '0 auto 24px',
              padding: `${config.styleConfig.pageMarginTop}mm ${config.styleConfig.pageMarginRight}mm ${config.styleConfig.pageMarginBottom}mm ${config.styleConfig.pageMarginLeft}mm`,
              background: '#fff',
              boxShadow: '0 18px 46px rgba(74,85,104,0.22)',
              borderRadius: 0,
              outline: '1px solid rgba(15,23,42,0.08)',
              boxSizing: 'border-box',
              display: 'flex',
              flexDirection: 'column',
            }}
          >
            {/* Page header */}
            <PageHeader config={config} />

            {/* Page body */}
            <div
              style={{
                flex: 1,
                columnCount,
                columnGap: columnCount > 1 ? '12mm' : undefined,
              }}
            >
              {pageItems.map((item) => {
                if (item.type === 'page_break') {
                  return null;
                }

                if (item.type === 'knowledge') {
                  return <KnowledgeBlock key={`knowledge-${pageIndex}-${item.title}`} item={item} />;
                }

                if (item.type === 'text') {
                  return <TextBlock key={`text-${pageIndex}-${item.title}`} item={item} config={config} />;
                }

                if (!item.question) {
                  return null;
                }

                questionNum += 1;

                return (
                  <HandoutQuestionBlock
                    key={item.question.question_id || `${pageIndex}-${questionNum}`}
                    question={item.question}
                    index={questionNum}
                    config={config}
                  />
                );
              })}
            </div>

            {/* Page footer */}
            <PageFooter config={config} pageNum={pageIndex + 1} />

            {/* Print-only header (repeated per printed page) */}
            <div className="print-only" style={{ display: 'none' }}>
              {config.title && (
                <div style={{ position: 'fixed', top: 0, left: 0, right: 0, textAlign: 'center', fontSize: 10, color: '#999', padding: '5mm 18mm' }}>
                  {config.title}
                </div>
              )}
            </div>
          </div>
        ))}
      </div>

      {/* Summary bar (screen-only) */}
      <div
        className="handout-screen-only"
        style={{
          textAlign: 'center',
          padding: '8px 0 24px',
          fontSize: 12,
          color: 'var(--color-text-muted)',
        }}
      >
        {config.showAnswers ? '教师版' : '学生版'} — 共 {pages.length} 页，{items.filter((it) => it.type === 'question').length} 题
      </div>
    </>
  );
}

function getEstimatedPageCapacity(config: HandoutConfig) {
  const pageSize = config.styleConfig.pageSize || 'A4';
  const orientation = config.styleConfig.pageOrientation || 'portrait';
  const layoutMode = config.styleConfig.layoutMode || 'paged-single';
  const base = pageSize === 'A3'
    ? orientation === 'landscape' ? 70 : 95
    : orientation === 'landscape' ? 38 : 58;
  const columnMultiplier = layoutMode === 'paged-double' ? 1.68 : 1;
  const fontMultiplier = 14 / Math.max(config.styleConfig.fontSize || 14, 10);
  return Math.max(24, Math.floor(base * columnMultiplier * fontMultiplier));
}

function estimateItemUnits(item: HandoutItem, config: HandoutConfig) {
  if (item.type === 'page_break') return 0;
  if (item.type === 'text') {
    if (item.blockKind === 'exam_title') return 8;
    if (item.blockKind === 'name_line') return 4;
    if (item.blockKind === 'section_title') return 4;
    return 5 + Math.ceil((item.content || '').length / 42);
  }
  if (item.type === 'knowledge') {
    return 8 + (item.points || []).length * 2 + Math.ceil((item.summary || '').length / 56);
  }
  const question = item.question;
  if (!question) return 8;
  const stemLength = (question.title || question.stem_text || '').length;
  const optionUnits = (question.options || []).reduce((sum, option) => sum + Math.max(2, Math.ceil((option.content || '').length / 34)), 0);
  const analysisUnits = config.showAnalysis && question.analysis ? Math.ceil(question.analysis.length / 48) : 0;
  const figureUnits = (question.figures || []).length * 9;
  return 8 + Math.ceil(stemLength / 42) + optionUnits + analysisUnits + figureUnits;
}

/** Split items into paper pages. Manual page breaks are respected; other content uses a practical height estimate. */
function splitIntoPages(items: HandoutItem[], config: HandoutConfig): HandoutItem[][] {
  const pages: HandoutItem[][] = [];
  let currentPage: HandoutItem[] = [];
  let currentUnits = 0;
  const pageCapacity = getEstimatedPageCapacity(config);

  for (const item of items) {
    if (item.type === 'page_break' && currentPage.length > 0) {
      pages.push(currentPage);
      currentPage = [];
      currentUnits = 0;
      continue;
    }
    if (item.type === 'page_break') continue;

    const itemUnits = estimateItemUnits(item, config);
    if (currentPage.length > 0 && currentUnits + itemUnits > pageCapacity) {
      pages.push(currentPage);
      currentPage = [];
      currentUnits = 0;
    }
    currentPage.push(item);
    currentUnits += itemUnits;
  }

  if (currentPage.length > 0) {
    pages.push(currentPage);
  }

  return pages.length > 0 ? pages : [[]];
}
