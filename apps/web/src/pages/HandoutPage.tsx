import { useCallback, useMemo, useState, type CSSProperties } from 'react';
import { useNavigate } from 'react-router-dom';

import HandoutDocument, { getHandoutPaginationReport } from '../components/handout/HandoutDocument';
import PrintPreflightPanel from '../components/handout/PrintPreflightPanel';
import LessonPackageTree from '../components/lesson/LessonPackageTree';
import { DEFAULT_CONFIG as DEFAULT_HF_CONFIG } from '../components/handout/HandoutHeaderFooterConfigPanel';
import { DEFAULT_STYLE_CONFIG } from '../components/handout/handoutStylePresets';
import { Button } from '../components/ui/Button';
import { EmptyState } from '../components/ui/EmptyState';
import { Input } from '../components/ui/Input';
import {
  deleteSavedLessonPackage,
  listSavedLessonPackages,
  loadSavedLessonPackage,
  loadCurrentLessonPackage,
  saveCurrentLessonPackage,
  saveLessonPackageToLibrary,
} from '../services/lessonPackage';
import { layoutModelToHandoutItems, lessonPackageToLayoutModel } from '../services/lessonLayoutModel';
import { validateLessonPackage } from '../services/lessonExport';
import type {
  HandoutConfig,
  HandoutItem,
  LessonPackage,
  PreflightRiskItem,
} from '../types';

function splitIntoPages(items: HandoutItem[]): HandoutItem[][] {
  const pages: HandoutItem[][] = [];
  let current: HandoutItem[] = [];

  for (const item of items) {
    if (item.type === 'page_break' && current.length > 0) {
      pages.push(current);
      current = [];
      continue;
    }
    current.push(item);
  }

  if (current.length > 0) {
    pages.push(current);
  }

  return pages.length > 0 ? pages : [[]];
}

function buildPreflightRisks(items: HandoutItem[], config: HandoutConfig): PreflightRiskItem[] {
  const pages = splitIntoPages(items);
  const risks: PreflightRiskItem[] = [];
  let globalQuestionIndex = 0;

  pages.forEach((pageItems, pageIndex) => {
    let pageQuestionCount = 0;

    pageItems.forEach((item) => {
      if (item.type !== 'question' || !item.question) {
        return;
      }

      globalQuestionIndex += 1;
      pageQuestionCount += 1;

      const textLength =
        (item.question.title || '').length +
        (config.showAnswers ? (item.question.answer || '').length : 0) +
        (config.showAnalysis ? (item.question.analysis || '').length : 0);

      if (textLength > 1400) {
        risks.push({
          pageIndex,
          pageLabel: `第 ${pageIndex + 1} 页`,
          questionIndex: globalQuestionIndex,
          questionId: item.question.question_id,
          severity: 'danger',
          message: `第 ${globalQuestionIndex} 题内容过长，打印时可能跨页截断，请重点检查。`,
        });
      } else if (textLength > 900) {
        risks.push({
          pageIndex,
          pageLabel: `第 ${pageIndex + 1} 页`,
          questionIndex: globalQuestionIndex,
          questionId: item.question.question_id,
          severity: 'warning',
          message: `第 ${globalQuestionIndex} 题内容偏长，建议核对题干、答案和解析的排版密度。`,
        });
      }

      if ((item.question.figures || []).length > 0) {
        risks.push({
          pageIndex,
          pageLabel: `第 ${pageIndex + 1} 页`,
          questionIndex: globalQuestionIndex,
          questionId: item.question.question_id,
          severity: 'warning',
          message: `第 ${globalQuestionIndex} 题含有图片，请确认图片大小和页边距是否协调。`,
        });
      }
    });

    if (pageQuestionCount >= 5) {
      risks.push({
        pageIndex,
        pageLabel: `第 ${pageIndex + 1} 页`,
        severity: 'warning',
        message: '本页题量较多，建议预览打印效果，避免视觉过于拥挤。',
      });
    }
  });

  return risks;
}

export default function HandoutPage() {
  const navigate = useNavigate();
  const [lessonPackage, setLessonPackage] = useState<LessonPackage | null>(() => loadCurrentLessonPackage());
  const [savedPackages, setSavedPackages] = useState(() => listSavedLessonPackages());
  const [preflightMode, setPreflightMode] = useState(false);
  const [previewZoom, setPreviewZoom] = useState(82);
  const [config, setConfig] = useState<HandoutConfig>(() => ({
    title: lessonPackage?.title || '物理讲义预览',
    subtitle: lessonPackage?.subtitle || '题目与知识点一体化讲义',
    showAnswers: true,
    showAnalysis: true,
    headerFooter: lessonPackage?.headerFooter || DEFAULT_HF_CONFIG,
    styleConfig: lessonPackage?.styleConfig || DEFAULT_STYLE_CONFIG,
  }));

  const items = useMemo(
    () => (lessonPackage ? layoutModelToHandoutItems(lessonPackageToLayoutModel(lessonPackage)) : []),
    [lessonPackage],
  );

  const paginationReport = useMemo(() => getHandoutPaginationReport(items, config), [items, config]);
  const pageCount = paginationReport.estimatedPageCount;
  const questionCount = useMemo(
    () => items.filter((item) => item.type === 'question').length,
    [items],
  );
  const knowledgeCount = lessonPackage?.knowledgeCards.length || 0;
  const risks = useMemo(() => buildPreflightRisks(items, config), [items, config]);

  const handlePrint = useCallback(() => {
    if (!lessonPackage) return;
    const nextPackage = {
      ...lessonPackage,
      title: config.title,
      subtitle: config.subtitle,
      headerFooter: config.headerFooter,
      styleConfig: config.styleConfig,
      updatedAt: new Date().toISOString(),
    };
    const exportIssues = validateLessonPackage(nextPackage);
    if (exportIssues.length > 0) {
      window.alert(`打印前检查未通过：${exportIssues.slice(0, 3).map((issue) => issue.message).join('；')}`);
      return;
    }
    saveCurrentLessonPackage(nextPackage);
    setLessonPackage(nextPackage);
    window.print();
  }, [config, lessonPackage]);

  const openSavedPackage = useCallback((id: string) => {
    const pkg = loadSavedLessonPackage(id);
    if (!pkg) return;
    setLessonPackage(pkg);
    saveCurrentLessonPackage(pkg);
    setConfig({
      title: pkg.title,
      subtitle: pkg.subtitle,
      showAnswers: true,
      showAnalysis: true,
      headerFooter: pkg.headerFooter || DEFAULT_HF_CONFIG,
      styleConfig: pkg.styleConfig || DEFAULT_STYLE_CONFIG,
    });
  }, []);

  const handleSaveCurrent = useCallback(() => {
    if (!lessonPackage) return;
    const nextPackage = {
      ...lessonPackage,
      title: config.title,
      subtitle: config.subtitle,
      headerFooter: config.headerFooter,
      styleConfig: config.styleConfig,
      updatedAt: new Date().toISOString(),
    };
    saveLessonPackageToLibrary(nextPackage);
    setLessonPackage(nextPackage);
    setSavedPackages(listSavedLessonPackages());
  }, [config, lessonPackage]);

  const handleDeleteSaved = useCallback((id: string) => {
    deleteSavedLessonPackage(id);
    setSavedPackages(listSavedLessonPackages());
  }, []);

  if (!lessonPackage || items.length === 0) {
    return (
      <EmptyState
        icon="📄"
        title="还没有可预览的讲义内容"
        description="先在组卷工作台里选择题目和知识点，系统会自动生成讲义结构。"
        action={{ label: '前往组卷工作台', onClick: () => navigate('/compose') }}
      />
    );
  }

  return (
    <div className="flex h-full bg-[var(--color-bg)]">
      <LessonPackageTree
        packages={savedPackages}
        activeId={lessonPackage.id}
        title="讲义文件树"
        emptyText="保存一次后，这里会长期保留你的讲义作品。"
        onOpen={openSavedPackage}
        onDelete={handleDeleteSaved}
        onSaveCurrent={handleSaveCurrent}
      />

      <div className="flex min-w-0 flex-1 flex-col">
        <div className="border-b border-[var(--color-border)] bg-[var(--color-bg-card)] px-4 py-3">
          <div className="flex flex-wrap items-center gap-2">
            <div className="min-w-[220px] flex-1">
              <Input label="讲义标题" value={config.title} onChange={(event) => setConfig((prev) => ({ ...prev, title: event.target.value }))} placeholder="输入讲义标题" />
            </div>
            <div className="min-w-[190px] flex-1">
              <Input label="副标题" value={config.subtitle} onChange={(event) => setConfig((prev) => ({ ...prev, subtitle: event.target.value }))} placeholder="输入副标题" />
            </div>
            <div className="flex items-end gap-1">
              <button type="button" onClick={() => setConfig((prev) => ({ ...prev, showAnswers: false, showAnalysis: false }))} className={`h-7 rounded px-2.5 text-xs font-semibold ${!config.showAnswers && !config.showAnalysis ? 'bg-[var(--color-accent)] text-white' : 'bg-[var(--color-bg-hover)] text-[var(--color-text-muted)]'}`}>学生版</button>
              <button type="button" onClick={() => setConfig((prev) => ({ ...prev, showAnswers: true, showAnalysis: true }))} className={`h-7 rounded px-2.5 text-xs font-semibold ${config.showAnswers && config.showAnalysis ? 'bg-[var(--color-accent)] text-white' : 'bg-[var(--color-bg-hover)] text-[var(--color-text-muted)]'}`}>教师版</button>
              <Button variant="secondary" size="sm" onClick={() => setPreflightMode((prev) => !prev)}>{preflightMode ? '返回预览' : '打印检查'}</Button>
              <Button variant="outline" size="sm" onClick={handleSaveCurrent}>保存</Button>
              <Button size="sm" onClick={handlePrint}>打印 / PDF</Button>
            </div>
          </div>
          <div className="mt-2 flex flex-wrap items-center justify-between gap-2 border-t border-[var(--color-border)] pt-2">
            <div className="flex flex-wrap gap-1.5 text-[11px] text-[var(--color-text-muted)]">
              <PreviewPill label="题目" value={`${questionCount} 题`} />
              <PreviewPill label="知识点" value={`${knowledgeCount} 个`} />
              <PreviewPill label="预估" value={`${pageCount} 页`} />
              {paginationReport.nearCapacityPageCount > 0 && <PreviewPill label="接近满页" value={`${paginationReport.nearCapacityPageCount} 页`} tone="warning" />}
            </div>
            <div className="flex items-center gap-1">
              <button type="button" onClick={() => setPreviewZoom((value) => Math.max(55, value - 10))} className="h-6 w-6 rounded bg-[var(--color-bg-hover)] text-xs text-[var(--color-text-secondary)]" title="缩小">−</button>
              <button type="button" onClick={() => setPreviewZoom(82)} className="h-6 min-w-10 rounded px-1 text-[11px] font-semibold tabular-nums text-[var(--color-text-secondary)]">{previewZoom}%</button>
              <button type="button" onClick={() => setPreviewZoom((value) => Math.min(115, value + 10))} className="h-6 w-6 rounded bg-[var(--color-bg-hover)] text-xs text-[var(--color-text-secondary)]" title="放大">+</button>
            </div>
          </div>
        </div>

        <div className="min-h-0 flex-1 overflow-auto bg-[var(--color-bg-hover)] px-5 py-5">
          <div className="mx-auto w-max min-w-full">
            <div className="mb-3 flex items-center justify-center gap-2 text-[11px] text-[var(--color-text-subtle)]">
              <span>{config.showAnswers || config.showAnalysis ? '教师版讲义' : '学生版讲义'}</span>
              <span>·</span>
              <span>{lessonPackage.source === 'compose' ? '组卷工作台生成' : '当前教学包'}</span>
            </div>
            <div style={{ zoom: previewZoom / 100 } as CSSProperties}>
              <HandoutDocument items={items} config={config} />
            </div>
          </div>
        </div>
      </div>

      {preflightMode && (
        <PrintPreflightPanel
          config={config}
          pageCount={pageCount}
          questionCount={questionCount}
          risks={risks}
          onPrint={handlePrint}
          onBack={() => setPreflightMode(false)}
        />
      )}
    </div>
  );
}

function PreviewPill({ label, value, tone }: { label: string; value: string; tone?: 'warning' }) {
  return (
    <span className={`rounded border px-2 py-1 ${tone === 'warning' ? 'border-[var(--color-orange)]/30 bg-[var(--color-orange-light)] text-[var(--color-orange)]' : 'border-[var(--color-border)] bg-[var(--color-bg-hover)]'}`}>
      {label} <b className="ml-0.5 text-[var(--color-text-secondary)]">{value}</b>
    </span>
  );
}
