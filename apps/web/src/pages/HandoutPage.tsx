import { useCallback, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import HandoutDocument from '../components/handout/HandoutDocument';
import PrintPreflightPanel from '../components/handout/PrintPreflightPanel';
import LessonPackageTree from '../components/lesson/LessonPackageTree';
import { DEFAULT_CONFIG as DEFAULT_HF_CONFIG } from '../components/handout/HandoutHeaderFooterConfigPanel';
import { DEFAULT_STYLE_CONFIG } from '../components/handout/handoutStylePresets';
import { Button } from '../components/ui/Button';
import { EmptyState } from '../components/ui/EmptyState';
import { Input } from '../components/ui/Input';
import {
  buildHandoutItemsFromLessonPackage,
  deleteSavedLessonPackage,
  listSavedLessonPackages,
  loadSavedLessonPackage,
  loadCurrentLessonPackage,
  saveCurrentLessonPackage,
  saveLessonPackageToLibrary,
} from '../services/lessonPackage';
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
  const [config, setConfig] = useState<HandoutConfig>(() => ({
    title: lessonPackage?.title || '物理讲义预览',
    subtitle: lessonPackage?.subtitle || '题目与知识点一体化讲义',
    showAnswers: true,
    showAnalysis: true,
    headerFooter: lessonPackage?.headerFooter || DEFAULT_HF_CONFIG,
    styleConfig: lessonPackage?.styleConfig || DEFAULT_STYLE_CONFIG,
  }));

  const items = useMemo(
    () => (lessonPackage ? buildHandoutItemsFromLessonPackage(lessonPackage) : []),
    [lessonPackage],
  );

  const pageCount = useMemo(() => splitIntoPages(items).length, [items]);
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
          <div className="flex flex-wrap items-center gap-3">
            <div className="min-w-[280px] flex-1">
              <Input
                label="讲义标题"
                value={config.title}
                onChange={(event) => setConfig((prev) => ({ ...prev, title: event.target.value }))}
                placeholder="输入讲义标题"
              />
            </div>
            <div className="min-w-[240px] flex-1">
              <Input
                label="副标题"
                value={config.subtitle}
                onChange={(event) => setConfig((prev) => ({ ...prev, subtitle: event.target.value }))}
                placeholder="输入副标题"
              />
            </div>
            <div className="flex items-end gap-2">
              <Button variant="outline" onClick={() => setConfig((prev) => ({ ...prev, showAnswers: !prev.showAnswers }))}>
                {config.showAnswers ? '隐藏答案' : '显示答案'}
              </Button>
              <Button variant="outline" onClick={() => setConfig((prev) => ({ ...prev, showAnalysis: !prev.showAnalysis }))}>
                {config.showAnalysis ? '隐藏解析' : '显示解析'}
              </Button>
              <Button variant="secondary" onClick={() => setPreflightMode((prev) => !prev)}>
                {preflightMode ? '返回预览' : '打印检查'}
              </Button>
              <Button variant="outline" onClick={handleSaveCurrent}>保存当前</Button>
              <Button onClick={handlePrint}>打印 / 导出</Button>
            </div>
          </div>

          <div className="mt-3 grid gap-2 md:grid-cols-4">
            <SummaryCard label="题目数量" value={`${questionCount} 题`} />
            <SummaryCard label="知识点卡片" value={`${knowledgeCount} 个`} />
            <SummaryCard label="预计页数" value={`${pageCount} 页`} />
            <SummaryCard label="当前模式" value={config.showAnalysis ? '教师版' : '学生版'} />
          </div>
        </div>

        <div className="min-h-0 flex-1 overflow-auto bg-[var(--color-bg-hover)] px-5 py-5">
          <div className="mx-auto max-w-[1160px]">
            <div className="mb-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-card)] px-4 py-3 shadow-sm">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <div className="text-sm font-semibold text-[var(--color-text-main)]">统一教学包驱动</div>
                  <div className="text-xs text-[var(--color-text-muted)]">
                    本页与组卷工作台、幻灯预览、课堂授课共用同一份题目与知识点结构。
                  </div>
                </div>
                <div className="flex flex-wrap gap-2 text-xs text-[var(--color-text-muted)]">
                  <Badge>{lessonPackage.source === 'compose' ? '来源：组卷工作台' : '来源：当前教学包'}</Badge>
                  <Badge>{lessonPackage.id}</Badge>
                </div>
              </div>
            </div>

            <HandoutDocument items={items} config={config} />
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

function SummaryCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-[var(--color-border)] bg-[var(--color-bg-hover)] px-4 py-3">
      <div className="text-xs text-[var(--color-text-muted)]">{label}</div>
      <div className="mt-1 text-lg font-semibold text-[var(--color-text)]">{value}</div>
    </div>
  );
}

function Badge({ children }: { children: string }) {
  return (
    <span className="pv-chip">
      {children}
    </span>
  );
}
