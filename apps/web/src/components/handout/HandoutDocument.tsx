import type { HandoutConfig, HandoutItem } from '../../types';
import { useEffect, useRef, useState, type ReactNode } from 'react';
import { useSortable } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { GripVertical } from 'lucide-react';
import LatexRenderer from '../render/LatexRenderer';
import HandoutQuestionBlock from './HandoutQuestionBlock';

interface Props {
  items: HandoutItem[];
  config: HandoutConfig;
  screenPagesPerRow?: number;
  screenCompact?: boolean;
  screenPageLimit?: number;
  paginationEngine?: 'estimated' | 'pagedjs';
  selectedItemId?: string | null;
  selectedItemIds?: string[];
  onItemSelect?: (itemId: string, additive?: boolean) => void;
  onItemEdit?: (itemId: string) => void;
  editingItemId?: string | null;
  renderItemEditor?: () => ReactNode;
  sortable?: boolean;
  renderItemActions?: (itemId: string) => ReactNode;
}

function CanvasNode({
  itemId,
  selected,
  editing,
  sortable,
  onSelect,
  onEdit,
  children,
}: {
  itemId: string;
  selected: boolean;
  editing: boolean;
  sortable: boolean;
  onSelect: (additive: boolean) => void;
  onEdit?: () => void;
  children: ReactNode;
}) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: itemId,
    disabled: !sortable || editing,
  });

  return (
    <div
      ref={setNodeRef}
      role="button"
      tabIndex={0}
      data-lesson-node-id={itemId}
      className={`pv-canvas-node ${selected ? 'is-selected' : ''} ${editing ? 'is-editing' : ''} ${isDragging ? 'is-dragging' : ''}`}
      style={{ transform: CSS.Transform.toString(transform), transition, zIndex: isDragging ? 20 : undefined }}
      onClick={(event) => { event.stopPropagation(); onSelect(event.ctrlKey || event.metaKey); }}
      onDoubleClick={(event) => { event.stopPropagation(); onEdit?.(); }}
      onKeyDown={(event) => {
        if (!editing && event.target === event.currentTarget && event.key === 'Enter') {
          event.preventDefault();
          onSelect(false);
          onEdit?.();
        }
      }}
    >
      {sortable && !editing && (
        <button
          type="button"
          className="pv-canvas-node__drag"
          aria-label="拖动调整顺序"
          title="拖动调整顺序"
          onClick={(event) => event.stopPropagation()}
          {...attributes}
          {...listeners}
        >
          <GripVertical size={14} />
        </button>
      )}
      {children}
      {selected && !editing && <span className="pv-canvas-node__hint">双击编辑</span>}
    </div>
  );
}

export interface HandoutPaginationReport {
  estimatedPageCount: number;
  nearCapacityPageCount: number;
  sparsePageCount: number;
  oversizedItemCount: number;
}

function buildPrintStyles(config: HandoutConfig) {
  const pageSize = config.styleConfig.pageSize || 'A4';
  const orientation = config.styleConfig.pageOrientation || 'portrait';

  return `
  @page {
    size: ${pageSize} ${orientation};
    margin: 0;
  }

  @media print {
    html, body {
      margin: 0 !important;
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
      min-height: auto !important;
      height: auto !important;
      page-break-after: auto !important;
      break-after: auto !important;
      border: none !important;
      border-radius: 0 !important;
      display: block !important;
      overflow: visible !important;
      background: #fff !important;
      outline: none !important;
    }

    .handout-page-body {
      display: block !important;
      overflow: visible !important;
      flex: none !important;
    }

    .handout-document {
      display: block !important;
      padding: 0 !important;
    }

    .handout-page + .handout-page {
      page-break-before: always !important;
      break-before: page !important;
    }

    .question-block {
      break-inside: ${config.styleConfig.keepQuestionTogether === false ? 'auto' : 'avoid'} !important;
      page-break-inside: ${config.styleConfig.keepQuestionTogether === false ? 'auto' : 'avoid'} !important;
    }

    .pv-question-stem-figure {
      break-inside: ${config.styleConfig.keepFigureWithStem === false ? 'auto' : 'avoid'} !important;
      page-break-inside: ${config.styleConfig.keepFigureWithStem === false ? 'auto' : 'avoid'} !important;
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

function getPageSizeMm(config: HandoutConfig) {
  const pageSize = config.styleConfig.pageSize || 'A4';
  const orientation = config.styleConfig.pageOrientation || 'portrait';
  const base = pageSize === 'A3'
    ? { width: 297, height: 420 }
    : { width: 210, height: 297 };

  return orientation === 'landscape'
    ? { width: base.height, height: base.width }
    : base;
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

function escapeCssContent(value: string) {
  return String(value || '').replace(/\\/g, '\\\\').replace(/"/g, '\\"').replace(/[\r\n]+/g, ' ').trim();
}

function buildPagedEngineStyles(config: HandoutConfig) {
  const page = getPageSizeMm(config);
  const sc = config.styleConfig;
  const header = config.headerFooter?.headerEnabled ? escapeCssContent(config.headerFooter.headerText) : '';
  const footer = config.headerFooter?.footerEnabled ? escapeCssContent(config.headerFooter.footerText) : '';
  const pageNumber = config.headerFooter?.showPageNumber ? ' "第 " counter(page) " 页"' : '';
  const pageFooter = `${footer ? `"${footer}"` : ''}${footer && pageNumber ? ' "  "' : ''}${pageNumber}` || 'none';
  return `
    @page {
      size: ${page.width}mm ${page.height}mm;
      margin: ${sc.pageMarginTop}mm ${sc.pageMarginRight}mm ${sc.pageMarginBottom}mm ${sc.pageMarginLeft}mm;
      ${header ? `@top-center { content: "${header}"; font-size: 9pt; color: #64748b; }` : ''}
      ${pageFooter !== 'none' ? `@bottom-center { content: ${pageFooter}; font-size: 8pt; color: #94a3b8; }` : ''}
    }
    .pv-paged-flow { font-family: ${getDocumentFontFamily(config)}; color: #1f2937; }
    .pv-paged-flow .question-block { break-inside: ${sc.keepQuestionTogether === false ? 'auto' : 'avoid'}; page-break-inside: ${sc.keepQuestionTogether === false ? 'auto' : 'avoid'}; }
    .pv-paged-flow .pv-question-stem-figure { break-inside: ${sc.keepFigureWithStem === false ? 'auto' : 'avoid'}; page-break-inside: ${sc.keepFigureWithStem === false ? 'auto' : 'avoid'}; }
    .pv-paged-flow .pv-paged-manual-break { break-before: page; page-break-before: always; height: 0; }
    .pv-paged-flow-body { column-count: ${config.styleConfig.layoutMode === 'paged-double' ? 2 : 1}; column-gap: 12mm; column-fill: auto; }
    .pv-paged-target .pagedjs_pages { display: grid; gap: 14mm; justify-content: center; }
    .pv-paged-target .pagedjs_page,
    .pv-paged-target .pagedjs_sheet,
    .pv-paged-target .pagedjs_pagebox {
      width: ${page.width}mm !important;
      min-width: ${page.width}mm !important;
      height: ${page.height}mm !important;
      min-height: ${page.height}mm !important;
      box-sizing: border-box !important;
    }
    .pv-paged-target .pagedjs_page { margin: 0 !important; box-shadow: 0 10px 28px rgba(74,85,104,.18); }
  `;
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
        marginBottom: 18,
        padding: '1px 0 10px',
        borderBottom: '1px solid #d8dee8',
      }}
    >
      <div style={{ marginBottom: 8, fontSize: 17, fontWeight: 700, lineHeight: 1.6, color: '#0f172a' }}>
        {item.title || '讲解'}
      </div>
      {item.summary && (
        <div style={{ marginBottom: item.points?.length ? 8 : 0, whiteSpace: 'pre-wrap', fontSize: 14, lineHeight: 1.9, color: '#1e293b' }}>
          <LatexRenderer text={item.summary} />
        </div>
      )}
      <div style={{ display: 'grid', gap: 6 }}>
        {(item.points || []).map((point, index) => (
          <div
            key={`${item.title}-${index}`}
            style={{
              display: 'flex',
              alignItems: 'flex-start',
              gap: 7,
              fontSize: 14,
              lineHeight: 1.9,
              color: '#1e293b',
            }}
          >
            <span style={{ color: '#64748b' }}>•</span>
            <LatexRenderer text={point} />
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
          <LatexRenderer text={item.content || ''} />
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
        <LatexRenderer text={item.content || ''} />
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
          <LatexRenderer text={item.content || ''} />
        </div>
      </div>
    );
  }

  if (item.blockKind === 'text_box') {
    return (
      <div
        className="question-block"
        style={{
          breakInside: 'avoid',
          pageBreakInside: 'avoid',
          marginBottom: 14,
          padding: '10px 12px',
          border: '1px solid #94a3b8',
          borderRadius: 2,
          background: '#ffffff',
        }}
      >
        {item.title && (
          <div style={{ marginBottom: 6, fontSize: 12, fontWeight: 700, color: '#334155' }}>
            {item.title}
          </div>
        )}
        <div
          style={{
            whiteSpace: 'pre-wrap',
            fontSize: localStyle.fontSize || config.styleConfig.fontSize,
            lineHeight: 1.75,
            color: '#1e293b',
            fontFamily: blockFontFamily,
            fontWeight: localStyle.fontWeight,
            textAlign: localStyle.textAlign,
          }}
        >
          <LatexRenderer text={item.content || ''} />
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
        <LatexRenderer text={item.content || ''} />
      </div>
    </div>
  );
}

function HandoutFlowContent({ items, config }: Pick<Props, 'items' | 'config'>) {
  let questionNum = 0;
  return (
    <div className="pv-paged-flow">
      <div className="pv-paged-flow-body">
        {items.map((item, index) => {
          if (item.type === 'page_break') return <div key={`break-${index}`} className="pv-paged-manual-break" />;
          if (item.type === 'knowledge') return <KnowledgeBlock key={`knowledge-${index}-${item.title}`} item={item} />;
          if (item.type === 'text') return <TextBlock key={`text-${index}-${item.title}`} item={item} config={config} />;
          if (!item.question) return null;
          questionNum += 1;
          return <HandoutQuestionBlock key={item.question.question_id || `question-${index}`} question={item.question} index={questionNum} config={config} />;
        })}
      </div>
    </div>
  );
}

/** Precise, on-demand browser pagination. It is intentionally separate from the fast edit preview. */
export function PagedHandoutDocument({ items, config }: Pick<Props, 'items' | 'config'>) {
  const sourceRef = useRef<HTMLDivElement | null>(null);
  const targetRef = useRef<HTMLDivElement | null>(null);
  const [status, setStatus] = useState<'rendering' | 'ready' | 'error'>('rendering');

  useEffect(() => {
    let cancelled = false;
    const source = sourceRef.current;
    const target = targetRef.current;
    if (!source || !target) return undefined;
    setStatus('rendering');
    const timer = window.setTimeout(() => {
      void import('pagedjs')
        .then(async ({ Previewer }) => {
          if (cancelled) return;
          target.replaceChildren();
          const previewer = new Previewer();
          const clone = source.cloneNode(true) as HTMLElement;
          clone.removeAttribute('style');
          await previewer.preview(clone, [], target);
          if (!cancelled) setStatus('ready');
        })
        .catch(() => {
          if (!cancelled) setStatus('error');
        });
    }, 0);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [config, items]);

  return (
    <>
      <style>{buildPagedEngineStyles(config)}</style>
      <div
        ref={sourceRef}
        aria-hidden="true"
        style={{ position: 'fixed', left: '-100000px', top: 0, width: `${getPageSizeMm(config).width}mm`, pointerEvents: 'none' }}
      >
        <HandoutFlowContent items={items} config={config} />
      </div>
      {status === 'rendering' && <div className="py-8 text-center text-sm text-[var(--color-text-muted)]">正在进行精确分页…</div>}
      {status === 'error' && <div className="py-8 text-center text-sm text-[var(--color-danger)]">精确分页暂不可用，已保留快速预览。</div>}
      <div ref={targetRef} className="pv-paged-target" aria-live="polite" />
    </>
  );
}

export default function HandoutDocument({ items, config, screenPagesPerRow = 1, screenCompact = false, screenPageLimit, paginationEngine = 'estimated', selectedItemId, selectedItemIds = [], onItemSelect, onItemEdit, editingItemId, renderItemEditor, sortable = false, renderItemActions }: Props) {
  if (!items || items.length === 0) {
    return (
      <div className="flex h-full items-center justify-center">
        <p className="text-sm" style={{ color: 'var(--color-text-muted)' }}>
          暂无题目
        </p>
      </div>
    );
  }

  if (paginationEngine === 'pagedjs') {
    return <PagedHandoutDocument items={items} config={config} />;
  }

  // Split items into pages based on page_break markers
  const pages = splitIntoPages(items, config);
  const visiblePages = screenPageLimit ? pages.slice(0, screenPageLimit) : pages;
  const pageDimensions = getPageDimensions(config);
  const isFlowLayout = config.styleConfig.layoutMode === 'flow';
  const columnCount = config.styleConfig.layoutMode === 'paged-double' ? 2 : 1;
  const documentFontFamily = getDocumentFontFamily(config);
  const pagesPerRow = isFlowLayout ? 1 : Math.max(1, screenPagesPerRow);
  const screenBlankPageCount = isFlowLayout || pagesPerRow <= 1
    ? 0
    : (pagesPerRow - (visiblePages.length % pagesPerRow)) % pagesPerRow;

  // Running question number counter across all pages
  let questionNum = 0;
  const selectable = (item: HandoutItem, child: ReactNode) => {
    if (!item.id || (!onItemSelect && !sortable)) return child;
    const selected = selectedItemIds.length > 0 ? selectedItemIds.includes(item.id) : item.id === selectedItemId;
    const editing = item.id === editingItemId;
    return (
      <CanvasNode
        key={item.id}
        itemId={item.id}
        selected={selected}
        editing={editing}
        sortable={sortable}
        onSelect={(additive) => onItemSelect?.(item.id!, additive)}
        onEdit={() => onItemEdit?.(item.id!)}
      >
        {editing && renderItemEditor ? renderItemEditor() : child}
        {selected && !editing && renderItemActions?.(item.id)}
      </CanvasNode>
    );
  };

  return (
    <>
      <style>{buildPrintStyles(config)}</style>

      <div
        className="handout-document"
        style={{
          padding: screenCompact ? 0 : '24px 0',
          fontFamily: documentFontFamily,
          display: isFlowLayout ? 'block' : 'grid',
          gridTemplateColumns: isFlowLayout ? undefined : `repeat(${pagesPerRow}, ${pageDimensions.width})`,
          justifyContent: 'center',
          alignItems: 'start',
          gap: isFlowLayout ? undefined : '14mm 10mm',
        }}
      >
        {visiblePages.map((pageItems, pageIndex) => (
          <div
            key={pageIndex}
            className="handout-page"
            style={{
              width: pageDimensions.width,
              minHeight: isFlowLayout ? 'auto' : pageDimensions.minHeight,
              margin: isFlowLayout ? '0 auto 24px' : 0,
              padding: `${config.styleConfig.pageMarginTop}mm ${config.styleConfig.pageMarginRight}mm ${config.styleConfig.pageMarginBottom}mm ${config.styleConfig.pageMarginLeft}mm`,
              background: '#fff',
              boxShadow: '0 10px 28px rgba(74,85,104,0.18)',
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
              className="handout-page-body"
              style={{
                flex: 1,
                columnCount,
                columnGap: columnCount > 1 ? '12mm' : undefined,
                columnFill: columnCount > 1 ? 'auto' : undefined,
              }}
            >
              {pageItems.map((item, itemIndex) => {
                if (item.type === 'page_break') {
                  return isFlowLayout
                    ? selectable(item, <div className="pv-flow-page-break"><span>分页</span></div>)
                    : null;
                }

                if (item.type === 'knowledge') {
                  return selectable(item, <KnowledgeBlock key={`knowledge-${pageIndex}-${itemIndex}-${item.id || item.title}`} item={item} />);
                }

                if (item.type === 'text') {
                  return selectable(item, <TextBlock key={`text-${pageIndex}-${itemIndex}-${item.id || item.title}`} item={item} config={config} />);
                }

                if (!item.question) {
                  return null;
                }

                questionNum += 1;

                return selectable(item,
                  <HandoutQuestionBlock
                    key={item.question.question_id || `${pageIndex}-${questionNum}`}
                    question={item.question}
                    index={questionNum}
                    config={config}
                  />,
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
        {Array.from({ length: screenBlankPageCount }).map((_, index) => (
          <div
            key={`screen-blank-page-${index}`}
            aria-hidden="true"
            className="handout-screen-only handout-page"
            style={{
              width: pageDimensions.width,
              minHeight: pageDimensions.minHeight,
              margin: 0,
              background: '#fff',
              boxShadow: '0 10px 28px rgba(74,85,104,0.14)',
              borderRadius: 0,
              outline: '1px solid rgba(15,23,42,0.08)',
              boxSizing: 'border-box',
            }}
          />
        ))}
      </div>

      {/* Summary bar (screen-only) */}
      <div
        className="handout-screen-only"
        style={{
          gridColumn: isFlowLayout ? undefined : `1 / span ${pagesPerRow}`,
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
  const layoutMode = config.styleConfig.layoutMode || 'paged-single';
  const page = getPageSizeMm(config);
  const sc = config.styleConfig;
  const headerReserveMm = config.headerFooter?.headerEnabled ? 8 : 0;
  const footerReserveMm = config.headerFooter?.footerEnabled === false ? 0 : 8;
  const titleReserveMm = config.title?.trim() || config.subtitle?.trim() ? 18 : 0;
  const usableHeightMm = Math.max(
    40,
    page.height - sc.pageMarginTop - sc.pageMarginBottom - headerReserveMm - footerReserveMm - titleReserveMm,
  );
  const lineHeightMm = Math.max(3.2, (Math.max(sc.fontSize || 14, 10) * Math.max(sc.lineHeight || 1.6, 1.2) * 25.4) / 96);
  const columns = layoutMode === 'paged-double' ? 2 : 1;

  // Keep a small safety margin because formulas/images do not map perfectly to text-line units.
  return Math.max(16, Math.floor((usableHeightMm / lineHeightMm) * columns * 0.86));
}

function estimateItemUnits(item: HandoutItem, config: HandoutConfig) {
  if (item.type === 'page_break') return 0;
  if (item.type === 'text') {
    if (item.blockKind === 'exam_title') return 4;
    if (item.blockKind === 'name_line') return 2;
    if (item.blockKind === 'section_title') return 3;
    if (item.blockKind === 'text_box') return 4 + Math.ceil((item.content || '').length / 60);
    return 3 + Math.ceil((item.content || '').length / 60);
  }

  if (item.type === 'knowledge') {
    return 5 + (item.points || []).length + Math.ceil((item.summary || '').length / 68);
  }
  const question = item.question;
  if (!question) return 8;
  const stemLength = (question.title || question.stem_text || '').length;
  const optionUnits = (question.options || []).reduce(
    (sum, option) => sum + 1 + Math.max(1, Math.ceil((option.content || '').length / 34)),
    0,
  );
  const answerUnits = config.showAnswers && question.answer
    ? 1 + Math.ceil(question.answer.length / 38)
    : 0;
  const analysisLines = Math.max(
    (question.analysis || '').split(/\r?\n/).filter(Boolean).length,
    Math.ceil((question.analysis || '').length / 42),
  );
  const analysisUnits = config.showAnalysis && question.analysis ? 2 + Math.ceil(analysisLines * 1.25) : 0;
  const figureUnits = (question.figures || []).reduce((total, figure) => {
    const displayScale = Math.min(100, Math.max(25, Number(figure.display_scale ?? 60))) / 60;
    return total + Math.max(6, Math.ceil(10 * (config.styleConfig.figureScale || 1) * displayScale));
  }, 0);
  return 5 + Math.ceil(stemLength / 40) + optionUnits + answerUnits + analysisUnits + figureUnits;
}

export function getHandoutPaginationReport(items: HandoutItem[], config: HandoutConfig): HandoutPaginationReport {
  const pageCapacity = getEstimatedPageCapacity(config);
  const pages = splitIntoPages(items, config);
  const oversizedItemCount = items.filter((item) => item.type !== 'page_break' && estimateItemUnits(item, config) > pageCapacity * 0.9).length;
  const nearCapacityPageCount = pages.filter((page) => {
    const units = page.reduce((total, item) => total + estimateItemUnits(item, config), 0);
    return units > pageCapacity * 0.96;
  }).length;
  const sparsePageCount = pages.slice(0, -1).filter((page) => {
    const units = page.reduce((total, item) => total + estimateItemUnits(item, config), 0);
    return units < pageCapacity * 0.28;
  }).length;

  return { estimatedPageCount: pages.length, nearCapacityPageCount, sparsePageCount, oversizedItemCount };
}

/** Split items into paper pages. Manual page breaks are respected; other content uses a practical height estimate. */
function splitIntoPages(items: HandoutItem[], config: HandoutConfig): HandoutItem[][] {
  if (config.styleConfig.layoutMode === 'flow') {
    return [items];
  }

  const pages: HandoutItem[][] = [];
  let currentPage: HandoutItem[] = [];
  let currentUnits = 0;
  const pageCapacity = getEstimatedPageCapacity(config);

  const fillRatio = Math.min(0.98, Math.max(0.78, (config.styleConfig.pageFillPercent ?? 90) / 100));

  for (let index = 0; index < items.length; index += 1) {
    const item = items[index];
    if (item.type === 'page_break' && currentPage.length > 0) {
      pages.push(currentPage);
      currentPage = [];
      currentUnits = 0;
      continue;
    }
    if (item.type === 'page_break') continue;

    const itemUnits = estimateItemUnits(item, config);
    const nextItem = items[index + 1];
    const keepWithNextUnits = item.type === 'text' && item.blockKind === 'section_title' && nextItem && nextItem.type !== 'page_break'
      ? estimateItemUnits(nextItem, config)
      : 0;
    const longQuestionStartsFresh = config.styleConfig.startLongQuestionOnNewPage !== false
      && item.type === 'question'
      && itemUnits > pageCapacity * 0.48
      && currentUnits > pageCapacity * 0.16;
    const pageFillLimit = pageCapacity * (item.type === 'question' ? fillRatio : Math.min(0.98, fillRatio + 0.04));
    if (currentPage.length > 0 && (longQuestionStartsFresh || currentUnits + itemUnits + keepWithNextUnits > pageFillLimit)) {
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
