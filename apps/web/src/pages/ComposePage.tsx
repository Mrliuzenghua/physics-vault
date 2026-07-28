import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';

import ComposeItemRow from '../components/compose/ComposeItemRow';
import PageRuler from '../components/compose/PageRuler';
import HandoutDocument from '../components/handout/HandoutDocument';
import HandoutHeaderFooterConfigPanel, {
  DEFAULT_CONFIG as DEFAULT_HF_CONFIG,
} from '../components/handout/HandoutHeaderFooterConfigPanel';
import HandoutStylePresetPanel from '../components/handout/HandoutStylePresetPanel';
import { DEFAULT_STYLE_CONFIG } from '../components/handout/handoutStylePresets';
import TeachingSlidePage from '../components/teaching/TeachingSlidePage';
import { Button } from '../components/ui/Button';
import { EmptyState } from '../components/ui/EmptyState';
import { Input } from '../components/ui/Input';
import { Select } from '../components/ui/Select';
import { Spinner } from '../components/ui/Spinner';
import { useBasket } from '../hooks/useBasket';
import { fetchQuestion, fetchQuestionsByIds, savePaperDraft } from '../services/api';
import {
  buildComposeDiagnostics,
  formatQuestionType,
  type ComposeDiagnosticReport,
} from '../services/composeDiagnostics';
import {
  buildHandoutItemsFromLessonPackage,
  buildSlideDeckFromLessonPackage,
  createLessonPackage,
  listSavedLessonPackages,
  saveCurrentLessonPackage,
  saveLessonPackageToLibrary,
} from '../services/lessonPackage';
import type {
  ComposeItem,
  ComposeSeparatorItem,
  ComposeTextItem,
  HandoutConfig,
  HandoutHeaderFooterConfig,
  HandoutLayoutMode,
  HandoutStyleConfig,
  TemplateMaterialPackage,
} from '../types';
import type { Question } from '../types';
import type { SlideDeckTemplate } from '../types/slides';

const SLIDE_DECK_TEMPLATE_LABELS: Record<SlideDeckTemplate, string> = {
  teach_practice_teach: '讲练讲',
  teach_then_practice: '先讲后练',
  practice_only: '只出题',
};

const PREVIEW_OPTIONS = [
  { value: 'A4', label: '讲义预览' },
  { value: 'slides', label: '幻灯预览' },
];
const LAYOUT_MODE_OPTIONS: Array<{ value: HandoutLayoutMode; label: string }> = [
  { value: 'flow', label: '流式布局' },
  { value: 'paged-single', label: '单列分页' },
  { value: 'paged-double', label: '双列分页' },
];
const ORIENTATION_OPTIONS: Array<{ value: HandoutStyleConfig['pageOrientation']; label: string }> = [
  { value: 'portrait', label: '竖版' },
  { value: 'landscape', label: '横版' },
];
const FONT_FAMILY_OPTIONS: Array<{ value: HandoutStyleConfig['fontFamily']; label: string }> = [
  { value: 'songti', label: '宋体' },
  { value: 'heiti', label: '黑体' },
  { value: 'kaiti', label: '楷体' },
  { value: 'fangsong', label: '仿宋' },
  { value: 'system', label: '系统' },
];

function makeId(prefix: string): string {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

function buildComposeItemsFromQuestions(questions: Question[]): ComposeItem[] {
  return questions.map((question) => ({
    type: 'question',
    id: question.question_id,
    questionId: question.question_id,
    question,
  }));
}

export default function ComposePage() {
  const navigate = useNavigate();
  const location = useLocation();
  const routeState = location.state as { materialPackage?: TemplateMaterialPackage } | null;
  const incomingPkg = routeState?.materialPackage;
  const { items: basketItems, remove: removeFromBasket, clear: clearBasket } = useBasket();
  const sessionIdRef = useRef(`lesson-current-${Date.now()}`);

  const [composeItems, setComposeItems] = useState<ComposeItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedIndex, setSelectedIndex] = useState<number>(-1);
  const [previewMode, setPreviewMode] = useState<'A4' | 'slides'>('A4');
  const [lessonTitle, setLessonTitle] = useState('流式学案');
  const [lessonSubtitle, setLessonSubtitle] = useState('知识点、文本说明与试题自由拼接');
  const [headerFooter, setHeaderFooter] = useState<HandoutHeaderFooterConfig>(DEFAULT_HF_CONFIG);
  const [styleConfig, setStyleConfig] = useState<HandoutStyleConfig>(DEFAULT_STYLE_CONFIG);
  const [slideTemplate, setSlideTemplate] = useState<SlideDeckTemplate>('teach_practice_teach');
  const [textBlockTitle, setTextBlockTitle] = useState('讲次导语');
  const [textBlockContent, setTextBlockContent] = useState('在这里写本讲目标、过渡说明或课堂提示。');
  const [separatorTitle, setSeparatorTitle] = useState('分页 / 分栏');
  const [savedCount, setSavedCount] = useState(0);
  const [draftSaveState, setDraftSaveState] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle');
  const [rightPanel, setRightPanel] = useState<'insert' | 'style'>('insert');
  const generatedKnowledgeCards: Array<{ id: string; title: string }> = [];
  const knowledgeSelection = '';
  const setKnowledgeSelection = (_value: string) => undefined;

  useEffect(() => {
    let cancelled = false;

    async function load() {
      if (incomingPkg && incomingPkg.questions.length > 0) {
        if (!cancelled) {
          setLessonTitle(incomingPkg.name || '流式学案');
          setComposeItems(buildComposeItemsFromQuestions(incomingPkg.questions));
          setLoading(false);
        }
        return;
      }

      if (basketItems.length === 0) {
        if (!cancelled) {
          setComposeItems([]);
          setLoading(false);
        }
        return;
      }

      let loaded: ComposeItem[];
      try {
        const questions = await fetchQuestionsByIds(basketItems.map((item) => item.question_id));
        const questionMap = new Map(questions.map((question) => [question.question_id, question]));
        loaded = basketItems.map((basketItem) => ({
          type: 'question',
          id: basketItem.question_id,
          questionId: basketItem.question_id,
          question: questionMap.get(basketItem.question_id),
        }));
      } catch {
        loaded = [];
        for (const basketItem of basketItems) {
          try {
            const question = await fetchQuestion(basketItem.question_id);
            loaded.push({
              type: 'question',
              id: basketItem.question_id,
              questionId: basketItem.question_id,
              question,
            });
          } catch {
            loaded.push({
              type: 'question',
              id: basketItem.question_id,
              questionId: basketItem.question_id,
            });
          }
        }
      }

      if (!cancelled) {
        setComposeItems(loaded);
        setLoading(false);
      }
    }

    void load();
    setSavedCount(listSavedLessonPackages().length);
    return () => {
      cancelled = true;
    };
  }, [basketItems, incomingPkg]);

  const previewLessonPackage = useMemo(
    () =>
      createLessonPackage({
        id: sessionIdRef.current,
        title: lessonTitle,
        subtitle: lessonSubtitle,
        source: incomingPkg ? 'template' : 'compose',
        composeItems,
        headerFooter,
        styleConfig,
        slideTemplate,
      }),
    [composeItems, headerFooter, incomingPkg, lessonSubtitle, lessonTitle, slideTemplate, styleConfig],
  );

  useEffect(() => {
    saveCurrentLessonPackage(previewLessonPackage);
  }, [previewLessonPackage]);

  const previewModel = useMemo((): { items: ReturnType<typeof buildHandoutItemsFromLessonPackage>; config: HandoutConfig } | null => {
    if (previewLessonPackage.nodes.length === 0) return null;
    return {
      items: buildHandoutItemsFromLessonPackage(previewLessonPackage),
      config: {
        title: previewLessonPackage.title,
        subtitle: previewLessonPackage.subtitle,
        showAnswers: true,
        showAnalysis: true,
        headerFooter,
        styleConfig,
      },
    };
  }, [headerFooter, previewLessonPackage, styleConfig]);

  const slideDeck = useMemo(
    () => buildSlideDeckFromLessonPackage(previewLessonPackage),
    [previewLessonPackage],
  );
  const diagnostics = useMemo(
    () => buildComposeDiagnostics(previewLessonPackage),
    [previewLessonPackage],
  );

  useEffect(() => {
    if (previewLessonPackage.nodes.length === 0) {
      setDraftSaveState('idle');
      return;
    }

    setDraftSaveState('saving');
    const timer = window.setTimeout(() => {
      void savePaperDraft(previewLessonPackage, diagnostics as unknown as Record<string, unknown>)
        .then(() => {
          setDraftSaveState('saved');
        })
        .catch(() => {
          setDraftSaveState('error');
        });
    }, 700);

    return () => window.clearTimeout(timer);
  }, [diagnostics, previewLessonPackage]);

  const selectedItem = selectedIndex >= 0 ? composeItems[selectedIndex] : null;
  const selectedTextItem = selectedItem?.type === 'text' ? selectedItem : null;
  const questionCount = previewLessonPackage.questions.length;
  const knowledgeCount = previewLessonPackage.knowledgeCards.length;
  const textCount = previewLessonPackage.textBlocks.length;
  const pageBreakCount = previewLessonPackage.nodes.filter((node) => node.type === 'page_break').length;
  const selectedLabel = selectedItem
    ? `${selectedItem.type} · ${'title' in selectedItem ? selectedItem.title : selectedItem.question?.title || selectedItem.questionId}`
    : '未选择';

  const insertAtSelection = useCallback((nextItem: ComposeItem) => {
    setComposeItems((prev) => {
      const position = selectedIndex >= 0 ? selectedIndex + 1 : prev.length;
      const next = [...prev];
      next.splice(position, 0, nextItem);
      setSelectedIndex(position);
      return next;
    });
  }, [selectedIndex]);

  const updateSelectedTextItem = useCallback((patch: Partial<ComposeTextItem>) => {
    setComposeItems((prev) => {
      if (selectedIndex < 0 || prev[selectedIndex]?.type !== 'text') return prev;
      return prev.map((item, index) => (
        index === selectedIndex && item.type === 'text'
          ? { ...item, ...patch, style: { ...item.style, ...patch.style } }
          : item
      ));
    });
  }, [selectedIndex]);

  const handleAddTextBlock = useCallback(() => {
    const title = textBlockTitle.trim();
    const content = textBlockContent.trim();
    if (!title || !content) return;
    const nextItem: ComposeTextItem = {
      type: 'text',
      id: makeId('text'),
      title,
      content,
    };
    insertAtSelection(nextItem);
  }, [insertAtSelection, textBlockContent, textBlockTitle]);

  const handleAddPresetTextBlock = useCallback((title: string, content: string, blockKind?: ComposeTextItem['blockKind'], style?: ComposeTextItem['style']) => {
    const nextItem: ComposeTextItem = {
      type: 'text',
      id: makeId('text'),
      title,
      content,
      blockKind,
      style,
    };
    insertAtSelection(nextItem);
  }, [insertAtSelection]);

  const handleAddExamTitle = useCallback(() => {
    handleAddPresetTextBlock('试卷大标题', `${lessonTitle || '物理试卷'}\n${lessonSubtitle || ''}`.trim());
  }, [handleAddPresetTextBlock, lessonSubtitle, lessonTitle]);

  const handleAddNameLine = useCallback(() => {
    handleAddPresetTextBlock('姓名信息栏', '班级：__________    姓名：__________    学号：__________    得分：__________');
  }, [handleAddPresetTextBlock]);

  const handleAddSectionTitle = useCallback(() => {
    handleAddPresetTextBlock('试卷小标题', '一、单项选择题');
  }, [handleAddPresetTextBlock]);

  const handleAddEditableExamTitle = useCallback(() => {
    handleAddPresetTextBlock('试卷大标题', `${lessonTitle || '物理试卷'}\n${lessonSubtitle || ''}`.trim(), 'exam_title', {
      fontFamily: styleConfig.fontFamily,
      fontSize: 22,
      fontWeight: 'bold',
      textAlign: 'center',
    });
  }, [handleAddPresetTextBlock, lessonSubtitle, lessonTitle, styleConfig.fontFamily]);

  const handleAddEditableNameLine = useCallback(() => {
    handleAddPresetTextBlock('姓名信息栏', '班级：__________    姓名：__________    学号：__________    得分：__________', 'name_line', {
      fontFamily: styleConfig.fontFamily,
      fontSize: 14,
      fontWeight: 'normal',
      textAlign: 'center',
    });
  }, [handleAddPresetTextBlock, styleConfig.fontFamily]);

  const handleAddEditableSectionTitle = useCallback(() => {
    handleAddPresetTextBlock('试卷小标题', '一、单项选择题', 'section_title', {
      fontFamily: styleConfig.fontFamily,
      fontSize: 16,
      fontWeight: 'bold',
      textAlign: 'left',
    });
  }, [handleAddPresetTextBlock, styleConfig.fontFamily]);

  void handleAddExamTitle;
  void handleAddNameLine;
  void handleAddSectionTitle;

  const handleAddPageBreak = useCallback(() => {
    const title = separatorTitle.trim() || '分页';
    const separator: ComposeSeparatorItem = {
      type: 'separator',
      id: makeId('break'),
      title,
    };
    insertAtSelection(separator);
  }, [insertAtSelection, separatorTitle]);

  const handleMoveUp = useCallback((index: number) => {
    if (index <= 0) return;
    setComposeItems((prev) => {
      const next = [...prev];
      [next[index - 1], next[index]] = [next[index], next[index - 1]];
      return next;
    });
    setSelectedIndex(index - 1);
  }, []);

  const handleMoveDown = useCallback((index: number) => {
    setComposeItems((prev) => {
      if (index >= prev.length - 1) return prev;
      const next = [...prev];
      [next[index], next[index + 1]] = [next[index + 1], next[index]];
      return next;
    });
    setSelectedIndex(index + 1);
  }, []);

  const handleRemove = useCallback((index: number) => {
    setComposeItems((prev) => {
      const item = prev[index];
      if (!item) return prev;
      if (item.type === 'question') {
        removeFromBasket(item.questionId);
      }
      const next = [...prev];
      next.splice(index, 1);
      return next;
    });
    setSelectedIndex(-1);
  }, [removeFromBasket]);

  const handleSaveCurrent = useCallback(() => {
    saveLessonPackageToLibrary(previewLessonPackage);
    setSavedCount(listSavedLessonPackages().length);
  }, [previewLessonPackage]);

  const handleClearAll = useCallback(() => {
    clearBasket();
    setComposeItems([]);
    setSelectedIndex(-1);
  }, [clearBasket]);

  const openLessonRoute = useCallback((path: '/handout' | '/slides' | '/classroom') => {
    saveCurrentLessonPackage(previewLessonPackage);
    navigate(path);
  }, [navigate, previewLessonPackage]);

  const updateStyleConfig = useCallback(
    <K extends keyof HandoutStyleConfig>(key: K, value: HandoutStyleConfig[K]) => {
      setStyleConfig((prev) => ({ ...prev, [key]: value }));
    },
    [],
  );

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="space-y-3 text-center">
          <Spinner size={32} className="text-[var(--color-accent)]" />
          <p className="text-sm text-[var(--color-text-muted)]">正在加载组卷内容…</p>
        </div>
      </div>
    );
  }

  if (composeItems.length === 0) {
    return (
      <EmptyState
        icon="🧩"
        title="当前还没有内容对象"
        description="先从题库里加入题目，接下来再把知识点卡片、文本说明、分页节点一起编排。"
        action={{ label: '前往题库浏览', onClick: () => navigate('/browse') }}
      />
    );
  }

  return (
    <div className="flex h-full flex-col overflow-hidden bg-[var(--color-bg)]">
      <div className="shrink-0 border-b border-[var(--color-border)] bg-[var(--color-bg-card)] px-4 py-3">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="flex min-w-0 flex-1 flex-wrap items-center gap-2">
            <div className="rounded-xl bg-[var(--color-accent)] px-3 py-2 text-sm font-semibold text-white">
              组卷工作台
            </div>
            <Input value={lessonTitle} onChange={(event) => setLessonTitle(event.target.value)} size="sm" wrapperClassName="w-48" />
            <Input value={lessonSubtitle} onChange={(event) => setLessonSubtitle(event.target.value)} size="sm" wrapperClassName="w-72" />
            <Select
              options={(Object.entries(SLIDE_DECK_TEMPLATE_LABELS) as [SlideDeckTemplate, string][]).map(([value, label]) => ({ value, label }))}
              value={slideTemplate}
              onChange={(event) => setSlideTemplate(event.target.value as SlideDeckTemplate)}
              size="sm"
              wrapperClassName="w-32"
            />
          </div>
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" onClick={() => openLessonRoute('/handout')}>讲义</Button>
            <Button variant="outline" size="sm" onClick={() => openLessonRoute('/slides')}>PPT预览</Button>
            <Button size="sm" onClick={() => openLessonRoute('/classroom')}>课堂授课</Button>
            <Button variant="secondary" size="sm" onClick={handleSaveCurrent}>保存</Button>
          </div>
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <div className="flex items-center gap-1 rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-hover)] p-1">
            {LAYOUT_MODE_OPTIONS.map((option) => (
              <button
                key={option.value}
                type="button"
                onClick={() => updateStyleConfig('layoutMode', option.value)}
                className={`h-8 rounded-lg px-3 text-xs font-semibold transition-colors ${
                  styleConfig.layoutMode === option.value
                    ? 'bg-[var(--color-bg-card)] text-[var(--color-accent)] shadow-sm'
                    : 'text-[var(--color-text-muted)] hover:text-[var(--color-text-main)]'
                }`}
              >
                {option.label}
              </button>
            ))}
          </div>
          <Select
            options={[
              { value: 'A4', label: 'A4' },
              { value: 'A3', label: 'A3' },
            ]}
            value={styleConfig.pageSize}
            onChange={(event) => updateStyleConfig('pageSize', event.target.value as HandoutStyleConfig['pageSize'])}
            size="sm"
            wrapperClassName="w-24"
          />
          <div className="flex items-center gap-1 rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-hover)] p-1">
            {ORIENTATION_OPTIONS.map((option) => (
              <button
                key={option.value}
                type="button"
                onClick={() => updateStyleConfig('pageOrientation', option.value)}
                className={`h-8 rounded-lg px-3 text-xs font-semibold transition-colors ${
                  styleConfig.pageOrientation === option.value
                    ? 'bg-[var(--color-bg-card)] text-[var(--color-accent)] shadow-sm'
                    : 'text-[var(--color-text-muted)] hover:text-[var(--color-text-main)]'
                }`}
              >
                {option.label}
              </button>
            ))}
          </div>
          <Select
            options={FONT_FAMILY_OPTIONS}
            value={styleConfig.fontFamily}
            onChange={(event) => updateStyleConfig('fontFamily', event.target.value as HandoutStyleConfig['fontFamily'])}
            size="sm"
            wrapperClassName="w-24"
          />
          <Select
            options={[
              { value: '12', label: '12号' },
              { value: '14', label: '14号' },
              { value: '16', label: '16号' },
              { value: '18', label: '18号' },
            ]}
            value={String(styleConfig.fontSize)}
            onChange={(event) => updateStyleConfig('fontSize', Number(event.target.value))}
            size="sm"
            wrapperClassName="w-24"
          />
          <div className="flex items-center gap-1 rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-hover)] p-1">
            {PREVIEW_OPTIONS.map((option) => (
              <button
                key={option.value}
                type="button"
                onClick={() => setPreviewMode(option.value as 'A4' | 'slides')}
                className={`h-8 rounded-lg px-3 text-xs font-semibold transition-colors ${
                  previewMode === option.value
                    ? 'bg-[var(--color-bg-card)] text-[var(--color-accent)] shadow-sm'
                    : 'text-[var(--color-text-muted)] hover:text-[var(--color-text-main)]'
                }`}
              >
                {option.label}
              </button>
            ))}
          </div>
          <span className="pv-chip bg-[var(--color-accent-light)] text-[var(--color-accent-dark)]">题目 {questionCount}</span>
          <span className="pv-chip">估分 {diagnostics.totalScore}</span>
          <span className="pv-chip">均难 {diagnostics.averageDifficulty || '未标注'}</span>
          <span className="pv-chip">知识点 {knowledgeCount}</span>
          <span className="pv-chip">文本 {textCount}</span>
          <span className="pv-chip">分页 {pageBreakCount}</span>
          <span className="ml-auto text-xs text-[var(--color-text-muted)]">当前选中：{selectedLabel}</span>
        </div>
      </div>

      <div className="flex min-h-0 flex-1">
        <aside className="flex w-[268px] shrink-0 flex-col bg-[var(--color-sidebar)] shadow-[inset_-1px_0_0_rgba(148,163,184,0.14)]">
          <div className="px-4 py-3">
            <div className="flex items-center justify-between">
              <div>
                <div className="text-sm font-semibold text-[var(--color-text-main)]">大纲</div>
                <div className="mt-0.5 text-xs text-[var(--color-text-muted)]">调整顺序</div>
              </div>
              <span className="rounded bg-[var(--color-bg-card)] px-2 py-1 text-xs text-[var(--color-text-muted)]">
                {composeItems.length}
              </span>
            </div>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto px-3 pb-3">
            <ComposeItemRow
              items={composeItems}
              selectedIndex={selectedIndex}
              onSelect={setSelectedIndex}
              onMoveUp={handleMoveUp}
              onMoveDown={handleMoveDown}
              onRemove={handleRemove}
            />
          </div>
          <div className="bg-[rgba(255,255,255,0.72)] p-3 shadow-[inset_0_1px_0_rgba(148,163,184,0.14)]">
            <div className="grid grid-cols-4 gap-2 text-center text-[11px]">
              <Metric label="题" value={questionCount} />
              <Metric label="知" value={knowledgeCount} />
              <Metric label="文" value={textCount} />
              <Metric label="页" value={pageBreakCount} />
            </div>
          </div>
        </aside>

        <main className="flex min-w-0 flex-1 flex-col bg-[#e6edf7]">
          <div className="flex h-11 shrink-0 items-center justify-between bg-[rgba(255,255,255,0.68)] px-4 shadow-[inset_0_-1px_0_rgba(148,163,184,0.14)]">
            <div className="flex items-center gap-2 text-xs text-[var(--color-text-muted)]">
              <span className="font-semibold text-[var(--color-text-main)]">
                {previewMode === 'A4' ? '讲义画布' : '幻灯画布'}
              </span>
              <span className="pv-chip">自动保存</span>
            </div>
            <div className="text-xs text-[var(--color-text-subtle)]">
              作品库 {savedCount}
            </div>
          </div>

          <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
            <div className="mx-auto w-full max-w-[1280px]">
              <div className="bg-transparent">
                <div className="hidden">
                  <div className="text-xs text-[var(--color-text-muted)]">
                    {previewMode === 'A4' ? 'A4 打印预览' : `${slideDeck.pages.length} 页幻灯`}
                  </div>
                </div>

                <div className="min-h-[calc(100vh-230px)] bg-[#dfe6f0]">
                  {!previewModel ? (
                    <div className="flex h-[680px] items-center justify-center text-[var(--color-text-subtle)]">暂无可预览内容</div>
                  ) : previewMode === 'A4' ? (
                    <div className="px-4 py-3">
                      <PageRuler styleConfig={styleConfig}>
                        <HandoutDocument items={previewModel.items} config={previewModel.config} />
                      </PageRuler>
                    </div>
                  ) : (
                    <div className="space-y-5 px-5 py-4">
                      {slideDeck.pages.slice(0, 5).map((page) => (
                        <div
                          key={page.id}
                          className="mx-auto flex max-w-[980px] flex-col overflow-hidden rounded-lg border border-[var(--color-border)] bg-white shadow-sm"
                          style={{ aspectRatio: '16 / 9' }}
                        >
                          {page.sections.length > 0 ? (
                            <TeachingSlidePage data={page} />
                          ) : (
                            <div className="flex flex-1 items-center justify-center text-sm text-[var(--color-text-subtle)]">
                              题目页会在完整幻灯预览中显示
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>

          <div className="flex h-8 shrink-0 items-center justify-between bg-[rgba(255,255,255,0.68)] px-4 text-xs text-[var(--color-text-muted)] shadow-[inset_0_1px_0_rgba(148,163,184,0.12)]">
            <div>当前对象：{selectedLabel}</div>
            <div>{previewLessonPackage.id}</div>
          </div>
        </main>

        <aside className="flex w-[272px] shrink-0 flex-col bg-[rgba(255,255,255,0.78)] shadow-[inset_1px_0_0_rgba(148,163,184,0.14)]">
          <div className="p-3">
            <div className="grid grid-cols-2 gap-1 rounded-xl bg-[var(--color-bg-hover)] p-1">
              {[
                ['insert', '插入'],
                ['style', '样式'],
              ].map(([value, label]) => (
                <button
                  key={value}
                  type="button"
                  onClick={() => setRightPanel(value as 'insert' | 'style')}
                  className={`h-8 rounded text-sm font-semibold transition-colors ${
                    rightPanel === value
                      ? 'bg-[var(--color-bg-card)] text-[var(--color-accent)] shadow-sm'
                      : 'text-[var(--color-text-muted)]'
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>

          <div className="px-3 pb-3">
            <QualityPanel report={diagnostics} saveState={draftSaveState} />
          </div>

          <div className="min-h-0 flex-1 overflow-y-auto px-3 pb-3">
            {rightPanel === 'insert' ? (
              <div className="space-y-3">
                {selectedTextItem && (
                  <section className="rounded-2xl bg-[rgba(255,255,255,0.95)] p-3 shadow-[0_8px_24px_rgba(148,163,184,0.12)]">
                    <div className="mb-3 text-sm font-semibold text-[var(--color-text-main)]">当前文本块</div>
                    <div className="space-y-3">
                      <Input
                        label="名称"
                        value={selectedTextItem.title}
                        onChange={(event) => updateSelectedTextItem({ title: event.target.value })}
                      />
                      <div>
                        <label className="mb-1 block text-xs font-medium text-[var(--color-text-secondary)]">内容</label>
                        <textarea
                          value={selectedTextItem.content}
                          onChange={(event) => updateSelectedTextItem({ content: event.target.value })}
                          rows={4}
                          className="w-full resize-none rounded-md border border-[var(--color-border)] bg-[var(--color-bg-card)] px-3 py-2 text-sm text-[var(--color-text)] outline-none focus:border-[var(--color-accent)]"
                        />
                      </div>
                      <div className="grid grid-cols-2 gap-2">
                        <Select
                          options={FONT_FAMILY_OPTIONS}
                          value={selectedTextItem.style?.fontFamily || styleConfig.fontFamily}
                          onChange={(event) => updateSelectedTextItem({ style: { fontFamily: event.target.value as HandoutStyleConfig['fontFamily'] } })}
                          size="sm"
                        />
                        <Select
                          options={[
                            { value: '12', label: '12号' },
                            { value: '14', label: '14号' },
                            { value: '16', label: '16号' },
                            { value: '18', label: '18号' },
                            { value: '22', label: '22号' },
                            { value: '26', label: '26号' },
                          ]}
                          value={String(selectedTextItem.style?.fontSize || styleConfig.fontSize)}
                          onChange={(event) => updateSelectedTextItem({ style: { fontSize: Number(event.target.value) } })}
                          size="sm"
                        />
                      </div>
                      <div className="grid grid-cols-4 gap-1">
                        {[
                          ['left', '左'],
                          ['center', '中'],
                          ['right', '右'],
                        ].map(([value, label]) => (
                          <button
                            key={value}
                            type="button"
                            onClick={() => updateSelectedTextItem({ style: { textAlign: value as NonNullable<ComposeTextItem['style']>['textAlign'] } })}
                            className={`h-8 rounded-md text-xs font-semibold ${
                              (selectedTextItem.style?.textAlign || 'left') === value
                                ? 'bg-[var(--color-accent)] text-white'
                                : 'bg-[var(--color-bg-hover)] text-[var(--color-text-muted)]'
                            }`}
                          >
                            {label}
                          </button>
                        ))}
                        <button
                          type="button"
                          onClick={() => updateSelectedTextItem({ style: { fontWeight: selectedTextItem.style?.fontWeight === 'bold' ? 'normal' : 'bold' } })}
                          className={`h-8 rounded-md text-xs font-semibold ${
                            selectedTextItem.style?.fontWeight === 'bold'
                              ? 'bg-[var(--color-accent)] text-white'
                              : 'bg-[var(--color-bg-hover)] text-[var(--color-text-muted)]'
                          }`}
                        >
                          加粗
                        </button>
                      </div>
                    </div>
                  </section>
                )}
                <section className="rounded-2xl bg-[rgba(255,255,255,0.9)] p-3 shadow-[0_8px_24px_rgba(148,163,184,0.12)]">
                  <div className="mb-3 text-sm font-semibold text-[var(--color-text-main)]">快速插入</div>
                  <div className="grid grid-cols-1 gap-2">
                    <Button variant="outline" className="justify-start" onClick={handleAddEditableExamTitle}>
                      插入试卷大标题
                    </Button>
                    <Button variant="outline" className="justify-start" onClick={handleAddEditableNameLine}>
                      插入姓名栏
                    </Button>
                    <Button variant="outline" className="justify-start" onClick={handleAddEditableSectionTitle}>
                      插入试卷小标题
                    </Button>
                    <Button variant="outline" className="justify-start" onClick={handleAddTextBlock}>
                      插入正文
                    </Button>
                    <Button variant="outline" className="hidden" onClick={handleAddTextBlock}>
                      插入当前知识点
                    </Button>
                    <Button variant="outline" className="justify-start" onClick={handleAddPageBreak}>
                      插入分页
                    </Button>
                  </div>
                </section>

                <section className="rounded-2xl bg-[rgba(255,255,255,0.9)] p-3 shadow-[0_8px_24px_rgba(148,163,184,0.12)]">
                  <div className="mb-3 text-sm font-semibold text-[var(--color-text-main)]">正文块</div>
                  <div className="space-y-3">
                    <Input label="小标题" value={textBlockTitle} onChange={(event) => setTextBlockTitle(event.target.value)} />
                    <div>
                      <label className="mb-1 block text-xs font-medium text-[var(--color-text-secondary)]">正文</label>
                      <textarea
                        value={textBlockContent}
                        onChange={(event) => setTextBlockContent(event.target.value)}
                        rows={5}
                        className="w-full resize-none rounded-md border border-[var(--color-border)] bg-[var(--color-bg-card)] px-3 py-2 text-sm text-[var(--color-text)] outline-none focus:border-[var(--color-accent)]"
                      />
                    </div>
                    <Button variant="outline" className="w-full" onClick={handleAddTextBlock}>插入正文</Button>
                  </div>
                </section>

                <section className="hidden">
                  <div className="mb-3 text-sm font-semibold text-[var(--color-text-main)]">知识点卡片</div>
                  <div className="space-y-3">
                    <Select
                      options={generatedKnowledgeCards.map((card) => ({ value: card.id, label: card.title }))}
                      value={knowledgeSelection}
                      onChange={(event) => setKnowledgeSelection(event.target.value)}
                      placeholder="选择一个知识点"
                    />
                    <Button variant="outline" className="hidden" onClick={handleAddTextBlock} disabled>
                      插入知识点
                    </Button>
                  </div>
                </section>

                <section className="rounded-2xl bg-[rgba(255,255,255,0.9)] p-3 shadow-[0_8px_24px_rgba(148,163,184,0.12)]">
                  <div className="mb-3 text-sm font-semibold text-[var(--color-text-main)]">分页符</div>
                  <div className="space-y-3">
                    <Input value={separatorTitle} onChange={(event) => setSeparatorTitle(event.target.value)} placeholder="分页标题" />
                    <Button variant="outline" className="w-full" onClick={handleAddPageBreak}>插入分页</Button>
                  </div>
                </section>
              </div>
            ) : (
              <div className="space-y-3">
                <section className="rounded-2xl bg-[rgba(255,255,255,0.9)] p-3 shadow-[0_8px_24px_rgba(148,163,184,0.12)]">
                  <div className="mb-3 text-sm font-semibold text-[var(--color-text-main)]">页眉页脚</div>
                  <HandoutHeaderFooterConfigPanel config={headerFooter} onChange={setHeaderFooter} />
                </section>
                <section className="rounded-2xl bg-[rgba(255,255,255,0.9)] p-3 shadow-[0_8px_24px_rgba(148,163,184,0.12)]">
                  <div className="mb-3 text-sm font-semibold text-[var(--color-text-main)]">页面样式</div>
                  <HandoutStylePresetPanel currentConfig={styleConfig} onApplyConfig={setStyleConfig} />
                </section>
              </div>
            )}
          </div>

          <div className="p-3 shadow-[inset_0_1px_0_rgba(148,163,184,0.12)]">
            <div className="mb-3 grid grid-cols-2 gap-2 text-xs">
              <span className="rounded-md bg-[var(--color-bg-hover)] px-2 py-1.5 text-[var(--color-text-muted)]">已保存 {savedCount}</span>
              <span className="rounded-md bg-[var(--color-bg-hover)] px-2 py-1.5 text-[var(--color-text-muted)]">对象 {composeItems.length}</span>
            </div>
            <div className="flex gap-2">
              <Button className="flex-1" onClick={handleSaveCurrent}>保存当前</Button>
              <Button variant="danger" className="flex-1" onClick={handleClearAll}>清空</Button>
            </div>
          </div>
        </aside>
      </div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-card)] px-2 py-2">
      <div className="text-sm font-semibold text-[var(--color-text-main)]">{value}</div>
      <div className="text-[10px] text-[var(--color-text-muted)]">{label}</div>
    </div>
  );
}

function QualityPanel({
  report,
  saveState,
}: {
  report: ComposeDiagnosticReport;
  saveState: 'idle' | 'saving' | 'saved' | 'error';
}) {
  const topTypes = Object.entries(report.typeDistribution).slice(0, 3);
  const saveLabel = {
    idle: '等待编辑',
    saving: '正在同步',
    saved: '已同步到草稿库',
    error: '本地已保存，草稿库同步失败',
  }[saveState];

  return (
    <section className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-card)] p-3">
      <div className="mb-3 flex items-center justify-between gap-2">
        <div className="text-sm font-semibold text-[var(--color-text-main)]">组卷诊断</div>
        <span className="rounded bg-[var(--color-bg-hover)] px-2 py-1 text-[10px] text-[var(--color-text-muted)]">
          {saveLabel}
        </span>
      </div>

      <div className="grid grid-cols-3 gap-2 text-center text-[11px]">
        <MiniStat label="估分" value={report.totalScore || 0} />
        <MiniStat label="均难" value={report.averageDifficulty || '-'} />
        <MiniStat label="考点" value={report.knowledgeCount || 0} />
      </div>

      {topTypes.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {topTypes.map(([type, count]) => (
            <span key={type} className="rounded bg-[var(--color-bg-hover)] px-2 py-1 text-[10px] text-[var(--color-text-muted)]">
              {formatQuestionType(type)} {count}
            </span>
          ))}
        </div>
      )}

      <div className="mt-3 space-y-1.5">
        {report.warnings.slice(0, 4).map((warning) => (
          <div
            key={warning.message}
            className={`rounded-md px-2 py-1.5 text-xs leading-5 ${
              warning.level === 'danger'
                ? 'bg-[var(--color-danger-soft)] text-[var(--color-danger)]'
                : warning.level === 'warning'
                  ? 'bg-amber-50 text-amber-700'
                  : 'bg-[var(--color-bg-hover)] text-[var(--color-text-muted)]'
            }`}
          >
            {warning.message}
          </div>
        ))}
        {report.warnings.length === 0 && (
          <div className="rounded-md bg-emerald-50 px-2 py-1.5 text-xs text-emerald-700">
            结构均衡，暂未发现明显风险。
          </div>
        )}
      </div>
    </section>
  );
}

function MiniStat({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="rounded-md bg-[var(--color-bg-hover)] px-2 py-2">
      <div className="text-sm font-semibold text-[var(--color-text-main)]">{value}</div>
      <div className="text-[10px] text-[var(--color-text-muted)]">{label}</div>
    </div>
  );
}
