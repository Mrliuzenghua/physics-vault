import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties, type SetStateAction } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { Virtuoso } from 'react-virtuoso';
import { DndContext, KeyboardSensor, PointerSensor, closestCenter, useSensor, useSensors, type DragEndEvent } from '@dnd-kit/core';
import { SortableContext, arrayMove, sortableKeyboardCoordinates, verticalListSortingStrategy } from '@dnd-kit/sortable';
import { ArrowDown, ArrowUp, Copy, Files, Trash2 } from 'lucide-react';

import PageRuler from '../components/compose/PageRuler';
import QuestionLiveEditor from '../components/editor/QuestionLiveEditor';
import StructuredTextEditor from '../components/editor/StructuredTextEditor';
import HandoutDocument, { getHandoutPaginationReport, type HandoutPaginationReport } from '../components/handout/HandoutDocument';
import { DEFAULT_CONFIG as DEFAULT_HF_CONFIG } from '../components/handout/HandoutHeaderFooterConfigPanel';
import { DEFAULT_STYLE_CONFIG } from '../components/handout/handoutStylePresets';
import TeachingSlidePage from '../components/teaching/TeachingSlidePage';
import { Button } from '../components/ui/Button';
import { Select } from '../components/ui/Select';
import { Spinner } from '../components/ui/Spinner';
import { useBasket } from '../hooks/useBasket';
import { useComposeDraftSession } from '../hooks/compose/useComposeDraftSession';
import { useComposeWorkbenchStore } from '../stores/useComposeWorkbenchStore';
import { savePaperDraft, searchQuestions } from '../services/api';
import { ApiError } from '../services/apiClient';
import {
  buildComposeDiagnostics,
  formatQuestionType,
  type ComposeDiagnosticReport,
  type ComposeDiagnosticWarning,
} from '../services/composeDiagnostics';
import {
  buildKnowledgeCardContent,
  buildKnowledgeCards,
  createLessonPackage,
  saveCurrentLessonPackage,
  saveLessonPackageToLibrary,
} from '../services/lessonPackage';
import {
  lessonDocumentToLessonPackage,
  lessonPackageToDocumentV2,
  saveCurrentLessonDocument,
} from '../services/lessonDocument';
import {
  buildLessonLayoutModel,
  layoutModelToHandoutItems,
  layoutModelToSlideDeck,
} from '../services/lessonLayoutModel';
import { applyTemplateToHeaderFooter, applyTemplateToStyleConfig, type TemplateApplyMode } from '../services/templateApplication';
import { getComposeUserSettings, saveComposeUserSettings, type ComposeUserSettings } from '../services/composeSettings';
import type {
  ComposeItem,
  ComposeSeparatorItem,
  ComposeTextItem,
  HandoutConfig,
  HandoutHeaderFooterConfig,
  HandoutStyleConfig,
  TemplateConfig,
  TemplateMaterialPackage,
} from '../types';
import type { Question } from '../types';
import type { SlideDeckTemplate } from '../types/slides';
import { getQuestionSourceLabel } from '../utils/questionSource';

const FONT_FAMILY_OPTIONS: Array<{ value: HandoutStyleConfig['fontFamily']; label: string }> = [
  { value: 'songti', label: '宋体' },
  { value: 'heiti', label: '黑体' },
  { value: 'kaiti', label: '楷体' },
  { value: 'fangsong', label: '仿宋' },
  { value: 'system', label: '系统' },
];

type AnswerExportMode = 'end_answer' | 'end_answer_analysis' | 'after_answer' | 'after_answer_analysis';

const ANSWER_EXPORT_OPTIONS: Array<{ value: AnswerExportMode; label: string }> = [
  { value: 'end_answer', label: '卷尾答案' },
  { value: 'end_answer_analysis', label: '卷尾答案和解析' },
  { value: 'after_answer', label: '题后答案' },
  { value: 'after_answer_analysis', label: '题后答案和解析' },
];

const PX_PER_MM = 96 / 25.4;
const RULER_LEFT_WIDTH_PX = 34;
const SPREAD_GAP_MM = 10;

interface MeasuredPageGroup {
  index: number;
  itemIds: string[];
  usedPercent: number;
}

interface ComposeSettingsSnapshot {
  title: string;
  subtitle: string;
  headerFooter: HandoutHeaderFooterConfig;
  styleConfig: HandoutStyleConfig;
  slideTemplate: SlideDeckTemplate;
}

interface TeachingBlueprintPreview {
  items: ComposeItem[];
  groups: Array<{ knowledge: string; questionCount: number; difficultyRange: string }>;
  preservedTextCount: number;
  removedPageBreakCount: number;
  compliance: string[];
}

interface TeachingBlueprintRules {
  targetQuestionCount: number;
  maxQuestionsPerKnowledge: number;
  requireComprehensiveQuestion: boolean;
}

function makeId(prefix: string): string {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

function getComposePageSizeMm(styleConfig: HandoutStyleConfig) {
  const base = styleConfig.pageSize === 'A3'
    ? { width: 297, height: 420 }
    : { width: 210, height: 297 };

  return styleConfig.pageOrientation === 'landscape'
    ? { width: base.height, height: base.width }
    : base;
}

function getPrimaryKnowledge(question: Question): string {
  return question.knowledge_points?.[0]?.topic3_name
    || question.knowledge_points?.[0]?.topic2_name
    || question.knowledge_points?.[0]?.topic1_name
    || question.knowledge_point?.split(/[\n,，、;；]+/).map((value) => value.trim()).find(Boolean)
    || '课堂练习';
}

function isEditableTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  return (
    target.tagName === 'INPUT' ||
    target.tagName === 'TEXTAREA' ||
    target.tagName === 'SELECT' ||
    target.isContentEditable
  );
}

export default function ComposePage() {
  const navigate = useNavigate();
  const location = useLocation();
  const routeState = location.state as {
    materialPackage?: TemplateMaterialPackage;
    templateConfig?: TemplateConfig;
    templateName?: string;
    templateApplyMode?: TemplateApplyMode;
    newDraft?: boolean;
  } | null;
  const incomingPkg = routeState?.materialPackage;
  const startNewDraft = routeState?.newDraft === true;
  const incomingTemplateConfig = routeState?.templateConfig || incomingPkg?.config;
  const { items: basketItems, remove: removeFromBasket, clear: clearBasket } = useBasket();
  const documentCanvasRef = useRef<HTMLDivElement | null>(null);

  const composeItems = useComposeWorkbenchStore((state) => state.items);
  const selectedIndex = useComposeWorkbenchStore((state) => state.selectedIndex);
  const documentRevision = useComposeWorkbenchStore((state) => state.revision);
  const savedRevision = useComposeWorkbenchStore((state) => state.savedRevision);
  const canUndoItems = useComposeWorkbenchStore((state) => state.past.length > 0);
  const canRedoItems = useComposeWorkbenchStore((state) => state.future.length > 0);
  const loadComposeItems = useComposeWorkbenchStore((state) => state.loadItems);
  const commitItems = useComposeWorkbenchStore((state) => state.commitItems);
  const updateItems = useComposeWorkbenchStore((state) => state.updateItems);
  const beginTransaction = useComposeWorkbenchStore((state) => state.beginTransaction);
  const commitTransaction = useComposeWorkbenchStore((state) => state.commitTransaction);
  const cancelTransaction = useComposeWorkbenchStore((state) => state.cancelTransaction);
  const setSelectedIndex = useComposeWorkbenchStore((state) => state.selectIndex);
  const undo = useComposeWorkbenchStore((state) => state.undo);
  const redo = useComposeWorkbenchStore((state) => state.redo);
  const markSaved = useComposeWorkbenchStore((state) => state.markSaved);
  const [previewMode, setPreviewMode] = useState<'A4' | 'slides'>('A4');
  const [userSettings] = useState<ComposeUserSettings>(() => getComposeUserSettings());
  const [renderAllPreviewPages, setRenderAllPreviewPages] = useState(false);
  const [screenPreviewPageLimit, setScreenPreviewPageLimit] = useState(3);
  const [documentZoom, setDocumentZoom] = useState(userSettings.documentZoom);
  const [zoomMode, setZoomMode] = useState<'fit-width' | 'manual'>(userSettings.zoomMode);
  const [canvasWidth, setCanvasWidth] = useState(0);
  const [showAnswers, setShowAnswers] = useState(userSettings.showAnswers);
  const [showAnalysis, setShowAnalysis] = useState(userSettings.showAnalysis);
  const [answerExportMode, setAnswerExportMode] = useState<AnswerExportMode>(userSettings.answerExportMode);
  const [outputProfile, setOutputProfile] = useState<'student' | 'teacher'>(userSettings.outputProfile);
  const [lessonTitle, setLessonTitleRaw] = useState('未命名试卷');
  const [lessonSubtitle, setLessonSubtitleRaw] = useState('');
  const [headerFooter, setHeaderFooterRaw] = useState<HandoutHeaderFooterConfig>(userSettings.headerFooter);
  const [styleConfig, setStyleConfigRaw] = useState<HandoutStyleConfig>(userSettings.styleConfig);
  const [slideTemplate, setSlideTemplateRaw] = useState<SlideDeckTemplate>(userSettings.slideTemplate);
  const [inspectorTab, setInspectorTab] = useState<'preflight' | 'view' | 'object'>('view');
  const [inspectorOpen, setInspectorOpen] = useState(true);
  const [outlineOpen, setOutlineOpen] = useState(true);
  const [outlineMode, setOutlineMode] = useState<'content' | 'pages'>('content');
  const [measuredPages, setMeasuredPages] = useState<MeasuredPageGroup[]>([]);
  const [measuredPaginationReport, setMeasuredPaginationReport] = useState<HandoutPaginationReport | null>(null);
  const [editingItemId, setEditingItemId] = useState<string | null>(null);
  const [selectedItemIds, setSelectedItemIds] = useState<string[]>([]);
  const [blueprintPreview, setBlueprintPreview] = useState<TeachingBlueprintPreview | null>(null);
  const settingsSnapshotRef = useRef<ComposeSettingsSnapshot>({ title: '未命名试卷', subtitle: '', headerFooter: DEFAULT_HF_CONFIG, styleConfig: DEFAULT_STYLE_CONFIG, slideTemplate: 'teach_practice_teach' });
  const settingsPastRef = useRef<ComposeSettingsSnapshot[]>([]);
  const settingsFutureRef = useRef<ComposeSettingsSnapshot[]>([]);
  const settingsHistoryEnabledRef = useRef(false);
  const settingsCoalesceRef = useRef({ key: '', at: 0 });
  const settingsLastChangeAtRef = useRef(0);
  const itemLastChangeAtRef = useRef(0);
  const [, setSettingsHistoryRevision] = useState(0);
  const [blueprintRulesOpen, setBlueprintRulesOpen] = useState(false);
  const [supplementCandidates, setSupplementCandidates] = useState<Question[]>([]);
  const [selectedSupplementIds, setSelectedSupplementIds] = useState<string[]>([]);
  const [supplementOpen, setSupplementOpen] = useState(false);
  const [supplementLoading, setSupplementLoading] = useState(false);
  const [supplementError, setSupplementError] = useState<string | null>(null);
  const [blueprintRules, setBlueprintRules] = useState<TeachingBlueprintRules>({
    targetQuestionCount: 0,
    maxQuestionsPerKnowledge: 0,
    requireComprehensiveQuestion: false,
  });
  const dndSensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

  const applySettingsSnapshot = useCallback((snapshot: ComposeSettingsSnapshot) => {
    settingsSnapshotRef.current = snapshot;
    setLessonTitleRaw(snapshot.title);
    setLessonSubtitleRaw(snapshot.subtitle);
    setHeaderFooterRaw(snapshot.headerFooter);
    setStyleConfigRaw(snapshot.styleConfig);
    setSlideTemplateRaw(snapshot.slideTemplate);
  }, []);

  const updateSettings = useCallback((key: keyof ComposeSettingsSnapshot, updater: (current: ComposeSettingsSnapshot) => ComposeSettingsSnapshot) => {
    const before = settingsSnapshotRef.current;
    const after = updater(before);
    if (after === before || Object.is(after[key], before[key])) return;
    const now = Date.now();
    const coalesced = settingsCoalesceRef.current.key === key && now - settingsCoalesceRef.current.at < 900;
    if (settingsHistoryEnabledRef.current && !coalesced) {
      settingsPastRef.current = [...settingsPastRef.current, before].slice(-60);
    }
    if (settingsHistoryEnabledRef.current) settingsFutureRef.current = [];
    settingsCoalesceRef.current = { key, at: now };
    settingsLastChangeAtRef.current = now;
    applySettingsSnapshot(after);
    setSettingsHistoryRevision((value) => value + 1);
  }, [applySettingsSnapshot]);

  const setLessonTitle = useCallback((action: SetStateAction<string>) => {
    updateSettings('title', (current) => ({ ...current, title: typeof action === 'function' ? action(current.title) : action }));
  }, [updateSettings]);
  const setLessonSubtitle = useCallback((action: SetStateAction<string>) => {
    updateSettings('subtitle', (current) => ({ ...current, subtitle: typeof action === 'function' ? action(current.subtitle) : action }));
  }, [updateSettings]);
  const setHeaderFooter = useCallback((action: SetStateAction<HandoutHeaderFooterConfig>) => {
    updateSettings('headerFooter', (current) => ({ ...current, headerFooter: typeof action === 'function' ? action(current.headerFooter) : action }));
  }, [updateSettings]);
  const setStyleConfig = useCallback((action: SetStateAction<HandoutStyleConfig>) => {
    updateSettings('styleConfig', (current) => ({ ...current, styleConfig: typeof action === 'function' ? action(current.styleConfig) : action }));
  }, [updateSettings]);
  useEffect(() => {
    settingsSnapshotRef.current = {
      ...settingsSnapshotRef.current,
      headerFooter: userSettings.headerFooter,
      styleConfig: userSettings.styleConfig,
      slideTemplate: userSettings.slideTemplate,
    };
  }, [userSettings]);

  useEffect(() => {
    saveComposeUserSettings({
      ...userSettings,
      headerFooter,
      styleConfig,
      slideTemplate,
      showAnswers,
      showAnalysis,
      outputProfile,
      answerExportMode,
      documentZoom,
      zoomMode,
    });
  }, [answerExportMode, documentZoom, headerFooter, outputProfile, showAnalysis, showAnswers, slideTemplate, styleConfig, userSettings, zoomMode]);

  const {
    draftId,
    draftSaveState,
    loading,
    recordSavedDraft,
    refreshDraft,
    serverDraftUpdatedAt,
    setDraftSaveState,
  } = useComposeDraftSession({
    basketItems,
    composeItems,
    documentRevision,
    incomingPackage: incomingPkg,
    loadComposeItems,
    savedRevision,
    setLessonSubtitle,
    setLessonTitle,
    startNewDraft,
    updateComposeItems: updateItems,
  });

  const undoSettings = useCallback(() => {
    const previous = settingsPastRef.current.at(-1);
    if (!previous) return;
    settingsPastRef.current = settingsPastRef.current.slice(0, -1);
    settingsFutureRef.current = [settingsSnapshotRef.current, ...settingsFutureRef.current].slice(0, 60);
    settingsCoalesceRef.current = { key: '', at: 0 };
    settingsLastChangeAtRef.current = Date.now();
    applySettingsSnapshot(previous);
    setSettingsHistoryRevision((value) => value + 1);
  }, [applySettingsSnapshot]);

  const redoSettings = useCallback(() => {
    const next = settingsFutureRef.current[0];
    if (!next) return;
    settingsFutureRef.current = settingsFutureRef.current.slice(1);
    settingsPastRef.current = [...settingsPastRef.current, settingsSnapshotRef.current].slice(-60);
    settingsCoalesceRef.current = { key: '', at: 0 };
    settingsLastChangeAtRef.current = Date.now();
    applySettingsSnapshot(next);
    setSettingsHistoryRevision((value) => value + 1);
  }, [applySettingsSnapshot]);

  useEffect(() => {
    if (!loading) settingsHistoryEnabledRef.current = true;
  }, [loading]);

  useEffect(() => {
    if (documentRevision > 0) itemLastChangeAtRef.current = Date.now();
  }, [documentRevision]);

  const canUndo = canUndoItems || settingsPastRef.current.length > 0;
  const canRedo = canRedoItems || settingsFutureRef.current.length > 0;
  const undoWorkspace = useCallback(() => {
    if (settingsPastRef.current.length > 0 && (!canUndoItems || settingsLastChangeAtRef.current >= itemLastChangeAtRef.current)) undoSettings();
    else undo();
  }, [canUndoItems, undo, undoSettings]);
  const redoWorkspace = useCallback(() => {
    if (settingsFutureRef.current.length > 0 && (!canRedoItems || settingsLastChangeAtRef.current >= itemLastChangeAtRef.current)) redoSettings();
    else redo();
  }, [canRedoItems, redo, redoSettings]);

  useEffect(() => {
    if (!incomingTemplateConfig) return;
    const applyMode = routeState?.templateApplyMode || 'overwrite';
    setStyleConfig((current) => applyTemplateToStyleConfig(current, incomingTemplateConfig, applyMode));
    setHeaderFooter((current) => applyTemplateToHeaderFooter(current, incomingTemplateConfig, applyMode));
    const nextShowAnswers = incomingTemplateConfig.show_answer ?? true;
    const nextShowAnalysis = incomingTemplateConfig.show_analysis ?? true;
    setShowAnswers(nextShowAnswers);
    setShowAnalysis(nextShowAnalysis);
    setOutputProfile(nextShowAnswers || nextShowAnalysis ? 'teacher' : 'student');
    setPreviewMode('A4');
    setZoomMode('fit-width');
  }, [incomingTemplateConfig, routeState?.templateApplyMode, setHeaderFooter, setStyleConfig]);

  const legacyLessonPackage = useMemo(
    () =>
      createLessonPackage({
        id: draftId,
        title: lessonTitle,
        subtitle: lessonSubtitle,
        source: incomingPkg ? 'template' : 'compose',
        composeItems,
        headerFooter,
        styleConfig,
        slideTemplate,
      }),
    [composeItems, draftId, headerFooter, incomingPkg, lessonSubtitle, lessonTitle, slideTemplate, styleConfig],
  );

  const previewLessonDocument = useMemo(
    () => lessonPackageToDocumentV2(legacyLessonPackage, documentRevision),
    [documentRevision, legacyLessonPackage],
  );

  const previewLessonPackage = useMemo(
    () => lessonDocumentToLessonPackage(previewLessonDocument),
    [previewLessonDocument],
  );

  const previewLayoutModel = useMemo(
    () => buildLessonLayoutModel(previewLessonDocument),
    [previewLessonDocument],
  );

  useEffect(() => {
    saveCurrentLessonDocument(previewLessonDocument);
    saveCurrentLessonPackage(previewLessonPackage);
  }, [previewLessonDocument, previewLessonPackage]);

  useEffect(() => {
    const node = documentCanvasRef.current;
    if (!node) return;

    const updateWidth = () => setCanvasWidth(node.clientWidth);
    updateWidth();

    if (typeof ResizeObserver === 'undefined') {
      window.addEventListener('resize', updateWidth);
      return () => window.removeEventListener('resize', updateWidth);
    }

    const observer = new ResizeObserver(updateWidth);
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  const previewModel = useMemo((): { items: ReturnType<typeof layoutModelToHandoutItems>; config: HandoutConfig } | null => {
    if (previewLayoutModel.blocks.length === 0) return null;
    return {
      items: layoutModelToHandoutItems(previewLayoutModel),
      config: {
        title: previewLayoutModel.title,
        subtitle: previewLayoutModel.subtitle,
        showAnswers,
        showAnalysis,
        headerFooter,
        styleConfig,
      },
    };
  }, [headerFooter, previewLayoutModel, showAnalysis, showAnswers, styleConfig]);

  const slideDeck = useMemo(
    () => layoutModelToSlideDeck(previewLayoutModel),
    [previewLayoutModel],
  );
  const diagnostics = useMemo(
    () => buildComposeDiagnostics(previewLessonPackage),
    [previewLessonPackage],
  );
  const paginationReport = useMemo(
    () => previewModel ? getHandoutPaginationReport(previewModel.items, previewModel.config) : null,
    [previewModel],
  );

  useEffect(() => {
    if (previewLessonPackage.nodes.length === 0) {
      setDraftSaveState('idle');
      return;
    }

    setDraftSaveState('saving');
    const revisionToSave = documentRevision;
    const timer = window.setTimeout(() => {
      void savePaperDraft(
        previewLessonPackage,
        diagnostics as unknown as Record<string, unknown>,
        revisionToSave,
        serverDraftUpdatedAt,
      )
        .then((draft) => {
          recordSavedDraft(draft);
          markSaved(revisionToSave);
          setDraftSaveState('saved');
        })
        .catch((error: unknown) => {
          if (error instanceof ApiError && error.status === 409) {
            void refreshDraft()
              .then((refreshed) => {
                if (!refreshed) setDraftSaveState('error');
              })
              .catch(() => setDraftSaveState('error'));
            return;
          }
          setDraftSaveState('error');
        });
    }, 700);

    return () => window.clearTimeout(timer);
  }, [diagnostics, documentRevision, markSaved, previewLessonPackage, recordSavedDraft, refreshDraft, serverDraftUpdatedAt, setDraftSaveState]);

  const selectedItem = selectedIndex >= 0 ? composeItems[selectedIndex] : null;
  const selectCanvasItem = useCallback((itemId: string, additive = false) => {
    const index = composeItems.findIndex((item) => item.id === itemId);
    if (index < 0) return;
    if (editingItemId && editingItemId !== itemId) {
      commitTransaction();
      setEditingItemId(null);
    }
    setSelectedIndex(index);
    setSelectedItemIds((current) => additive
      ? current.includes(itemId) ? current.filter((id) => id !== itemId) : [...current, itemId]
      : [itemId]);
    setInspectorTab('object');
  }, [commitTransaction, composeItems, editingItemId, setSelectedIndex]);
  const editCanvasItem = useCallback((itemId: string) => {
    const index = composeItems.findIndex((item) => item.id === itemId);
    if (index < 0) return;
    if (editingItemId && editingItemId !== itemId) commitTransaction();
    setSelectedIndex(index);
    beginTransaction();
    setEditingItemId(itemId);
  }, [beginTransaction, commitTransaction, composeItems, editingItemId, setSelectedIndex]);
  const finishInlineEdit = useCallback(() => {
    commitTransaction();
    setEditingItemId(null);
  }, [commitTransaction]);
  const cancelInlineEdit = useCallback(() => {
    cancelTransaction();
    setEditingItemId(null);
  }, [cancelTransaction]);
  const handleCanvasDragEnd = useCallback(({ active, over }: DragEndEvent) => {
    if (!over || active.id === over.id) return;
    const from = composeItems.findIndex((item) => item.id === active.id);
    const to = composeItems.findIndex((item) => item.id === over.id);
    if (from < 0 || to < 0) return;
    commitItems(arrayMove(composeItems, from, to), to);
  }, [commitItems, composeItems]);
  const locateQuestion = useCallback((questionId: string) => {
    const index = composeItems.findIndex((item) => item.type === 'question' && item.questionId === questionId);
    if (index < 0) return;
    const itemId = composeItems[index].id;
    setSelectedIndex(index);
    window.requestAnimationFrame(() => {
      document.querySelector(`[data-lesson-node-id="${CSS.escape(itemId)}"]`)?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    });
  }, [composeItems, setSelectedIndex]);
  const locateItem = useCallback((itemId: string) => {
    const index = composeItems.findIndex((item) => item.id === itemId);
    if (index < 0) return;
    setSelectedIndex(index);
    setSelectedItemIds([itemId]);
    window.requestAnimationFrame(() => {
      document.querySelector(`[data-lesson-node-id="${CSS.escape(itemId)}"]`)?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    });
  }, [composeItems, setSelectedIndex]);
  const fixDiagnosticWarning = useCallback((warning: ComposeDiagnosticWarning) => {
    if (!warning.questionId) return;
    const index = composeItems.findIndex((item) => item.type === 'question' && item.questionId === warning.questionId);
    if (index < 0) return;
    if (warning.code === 'figure') {
      const next = composeItems.map((item, itemIndex) => itemIndex === index && item.type === 'question' && item.question
        ? { ...item, question: { ...item.question, figures: (item.question.figures || []).map((figure) => ({ ...figure, display_scale: Math.min(100, Math.max(25, Number(figure.display_scale ?? 60))) })) } }
        : item);
      commitItems(next, index);
      setSelectedItemIds([composeItems[index].id]);
      return;
    }
    editCanvasItem(composeItems[index].id);
  }, [commitItems, composeItems, editCanvasItem]);
  const questionCount = previewLessonPackage.questions.length;
  const knowledgeCount = previewLessonPackage.knowledgeCards.length;
  const textCount = previewLessonPackage.textBlocks.length;
  const pageBreakCount = previewLessonPackage.nodes.filter((node) => node.type === 'page_break').length;
  const documentPagesPerRow = 1;
  const documentOrientationLabel = styleConfig.pageOrientation === 'landscape' ? '横向' : '竖向';
  const documentColumnsLabel = styleConfig.layoutMode === 'flow'
    ? '流式'
    : styleConfig.layoutMode === 'paged-double' ? '双栏' : '单栏';
  const documentLayoutLabel = `${styleConfig.pageSize} ${documentOrientationLabel}${documentColumnsLabel}`;
  const documentPageSizeMm = getComposePageSizeMm(styleConfig);
  const documentSpreadWidthPx =
    RULER_LEFT_WIDTH_PX +
    (documentPageSizeMm.width * documentPagesPerRow + SPREAD_GAP_MM * (documentPagesPerRow - 1)) * PX_PER_MM;
  const inspectorReservedWidth = 0;
  const fitZoom = canvasWidth > 0
    ? Math.max(45, Math.min(135, Math.floor(((canvasWidth - 64 - inspectorReservedWidth) / documentSpreadWidthPx) * 100)))
    : documentZoom;
  const effectiveZoom = zoomMode === 'fit-width' ? fitZoom : documentZoom;

  useEffect(() => {
    if (!previewModel || previewMode !== 'A4' || composeItems.length === 0) {
      setMeasuredPages([]);
      setMeasuredPaginationReport(null);
      return undefined;
    }
    const canvas = documentCanvasRef.current;
    if (!canvas) return undefined;
    let frame = 0;

    const measure = () => {
      const zoom = Math.max(0.01, effectiveZoom / 100);
      const page = getComposePageSizeMm(styleConfig);
      const headerReserve = headerFooter.headerEnabled ? 8 : 0;
      const footerReserve = headerFooter.footerEnabled === false ? 0 : 8;
      const titleReserve = lessonTitle.trim() || lessonSubtitle.trim() ? 18 : 0;
      const usableHeight = Math.max(160, (page.height - styleConfig.pageMarginTop - styleConfig.pageMarginBottom - headerReserve - footerReserve - titleReserve) * PX_PER_MM * zoom);
      const fillLimit = usableHeight * Math.min(0.98, Math.max(0.78, (styleConfig.pageFillPercent ?? 90) / 100));
      const heights = new Map<string, number>();
      canvas.querySelectorAll<HTMLElement>('[data-lesson-node-id]').forEach((element) => {
        const itemId = element.dataset.lessonNodeId;
        if (itemId) heights.set(itemId, element.getBoundingClientRect().height);
      });
      if (heights.size === 0) return;

      const groups: MeasuredPageGroup[] = [];
      let currentIds: string[] = [];
      let currentHeight = 0;
      let oversizedItemCount = 0;
      const finishPage = () => {
        if (currentIds.length === 0) return;
        groups.push({ index: groups.length, itemIds: currentIds, usedPercent: Math.min(199, Math.round((currentHeight / usableHeight) * 100)) });
        currentIds = [];
        currentHeight = 0;
      };

      for (const item of composeItems) {
        if (item.type === 'separator') {
          finishPage();
          continue;
        }
        const itemHeight = heights.get(item.id) || 0;
        if (itemHeight > usableHeight * 0.9) oversizedItemCount += 1;
        const startLongFresh = styleConfig.startLongQuestionOnNewPage !== false
          && item.type === 'question'
          && itemHeight > usableHeight * 0.48
          && currentHeight > usableHeight * 0.16;
        if (currentIds.length > 0 && (startLongFresh || currentHeight + itemHeight > fillLimit)) finishPage();
        currentIds.push(item.id);
        currentHeight += itemHeight;
      }
      finishPage();
      const normalizedGroups = groups.length > 0 ? groups : [{ index: 0, itemIds: [], usedPercent: 0 }];
      setMeasuredPages((current) => JSON.stringify(current) === JSON.stringify(normalizedGroups) ? current : normalizedGroups);
      const report = {
        estimatedPageCount: normalizedGroups.length,
        nearCapacityPageCount: normalizedGroups.filter((group) => group.usedPercent >= 92).length,
        sparsePageCount: normalizedGroups.slice(0, -1).filter((group) => group.usedPercent < 28).length,
        oversizedItemCount,
      };
      setMeasuredPaginationReport((current) => JSON.stringify(current) === JSON.stringify(report) ? current : report);
    };

    const scheduleMeasure = () => {
      window.cancelAnimationFrame(frame);
      frame = window.requestAnimationFrame(measure);
    };
    scheduleMeasure();
    const observer = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(scheduleMeasure);
    if (observer) observer.observe(canvas);
    window.addEventListener('resize', scheduleMeasure);
    return () => {
      window.cancelAnimationFrame(frame);
      observer?.disconnect();
      window.removeEventListener('resize', scheduleMeasure);
    };
  }, [composeItems, effectiveZoom, headerFooter, lessonSubtitle, lessonTitle, previewMode, previewModel, styleConfig]);

  const effectivePaginationReport = measuredPaginationReport || paginationReport;

  useEffect(() => {
    setScreenPreviewPageLimit(3);
  }, [documentRevision, previewMode, styleConfig.layoutMode, styleConfig.pageOrientation]);

  useEffect(() => {
    const canvas = documentCanvasRef.current;
    const totalPages = effectivePaginationReport?.estimatedPageCount || 0;
    if (!canvas || previewMode !== 'A4' || renderAllPreviewPages || totalPages <= screenPreviewPageLimit) return;

    const revealNearbyPages = () => {
      const remaining = canvas.scrollHeight - canvas.scrollTop - canvas.clientHeight;
      if (remaining > canvas.clientHeight * 0.75) return;
      setScreenPreviewPageLimit((current) => Math.min(totalPages, current + 2));
    };

    canvas.addEventListener('scroll', revealNearbyPages, { passive: true });
    return () => canvas.removeEventListener('scroll', revealNearbyPages);
  }, [effectivePaginationReport?.estimatedPageCount, previewMode, renderAllPreviewPages, screenPreviewPageLimit]);

  useEffect(() => {
    if (composeItems.length === 0) {
      if (selectedIndex !== -1) setSelectedIndex(-1);
      return;
    }
    if (selectedIndex < 0 || selectedIndex >= composeItems.length) setSelectedIndex(0);
  }, [composeItems.length, selectedIndex, setSelectedIndex]);

  const insertAtSelection = useCallback((nextItem: ComposeItem) => {
    const position = selectedIndex >= 0 ? selectedIndex + 1 : composeItems.length;
    const next = [...composeItems];
    next.splice(position, 0, nextItem);
    commitItems(next, position);
  }, [commitItems, composeItems, selectedIndex]);

  const updateSelectedTextItem = useCallback((patch: Partial<ComposeTextItem>) => {
    // Continuous text editing: mutate without committing history (avoid one entry per keystroke)
    updateItems((prev) => {
      if (selectedIndex < 0 || prev[selectedIndex]?.type !== 'text') return prev;
      return prev.map((item, index) => (
        index === selectedIndex && item.type === 'text'
          ? { ...item, ...patch, style: { ...item.style, ...patch.style } }
          : item
      ));
    });
  }, [selectedIndex, updateItems]);

  const updateSelectedItem = useCallback((updater: (item: ComposeItem) => ComposeItem) => {
    updateItems((prev) => {
      if (selectedIndex < 0 || !prev[selectedIndex]) return prev;
      return prev.map((item, index) => (index === selectedIndex ? updater(item) : item));
    });
  }, [selectedIndex, updateItems]);

  const updateSelectedQuestion = useCallback((patch: Partial<Question>) => {
    updateSelectedItem((item) => {
      if (item.type !== 'question' || !item.question) return item;
      return { ...item, question: { ...item.question, ...patch } };
    });
  }, [updateSelectedItem]);

  const handleAddTextBlock = useCallback(() => {
    const nextItem: ComposeTextItem = {
      type: 'text',
      id: makeId('text'),
      title: '说明段落',
      content: '在这里写本讲目标、过渡说明或课堂提示。',
      blockKind: 'body',
    };
    insertAtSelection(nextItem);
  }, [insertAtSelection]);

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

  const handleAddTextBox = useCallback(() => {
    handleAddPresetTextBlock('文本框', '在这里输入提示、说明、实验步骤或留空区域。', 'text_box', {
      fontFamily: styleConfig.fontFamily,
      fontSize: 12,
      fontWeight: 'normal',
      textAlign: 'left',
    });
  }, [handleAddPresetTextBlock, styleConfig.fontFamily]);

  const handleAddPageBreak = useCallback(() => {
    const separator: ComposeSeparatorItem = {
      type: 'separator',
      id: makeId('break'),
      title: '分页 / 分栏',
    };
    insertAtSelection(separator);
  }, [insertAtSelection]);

  const handleOrganizeByKnowledge = useCallback(() => {
    let previousKnowledge = '';
    const questions = composeItems
      .filter((item): item is Extract<ComposeItem, { type: 'question' }> => item.type === 'question' && Boolean(item.question))
      .map((item) => item.question!);
    const knowledgeCards = buildKnowledgeCards(questions);
    const cardByTitle = new Map(knowledgeCards.map((card) => [card.title, card]));
    const findKnowledgeCard = (title: string) => cardByTitle.get(title)
      || knowledgeCards.find((card) => title.endsWith(`：${card.title}`) || card.title.endsWith(`：${title}`));
    const existingKnowledgeIds = new Set(composeItems
      .filter((item): item is Extract<ComposeItem, { type: 'knowledge' }> => item.type === 'knowledge')
      .map((item) => item.knowledgeId));
    const existingCanonicalIds = new Set(composeItems
      .filter((item): item is Extract<ComposeItem, { type: 'knowledge' }> => item.type === 'knowledge')
      .map((item) => findKnowledgeCard(item.title)?.id)
      .filter((id): id is string => Boolean(id)));
    const emittedKnowledgeIds = new Set<string>();
    const pointsForCard = (points: string[]) => {
      const pointLimit = incomingTemplateConfig?.knowledge_length === 'short'
        ? 4
        : incomingTemplateConfig?.knowledge_length === 'medium'
          ? 6
          : points.length;
      return points.slice(0, pointLimit);
    };
    const next = composeItems.reduce<ComposeItem[]>((items, item) => {
      if (item.type === 'knowledge') {
        const refreshedCard = findKnowledgeCard(item.title);
        if (refreshedCard && emittedKnowledgeIds.has(refreshedCard.id)) return items;
        if (refreshedCard) emittedKnowledgeIds.add(refreshedCard.id);
        const fallbackContent = refreshedCard ? null : buildKnowledgeCardContent(item.title);
        items.push(refreshedCard ? {
          ...item,
          knowledgeId: refreshedCard.id,
          summary: refreshedCard.summary,
          points: pointsForCard(refreshedCard.points),
        } : {
          ...item,
          summary: fallbackContent!.summary,
          points: pointsForCard(fallbackContent!.points),
        });
        return items;
      }
      if (item.type !== 'question' || !item.question) {
        items.push(item);
        return items;
      }
      const knowledge = item.question.knowledge_points?.[0]?.topic3_name
        || item.question.knowledge_points?.[0]?.topic2_name
        || item.question.knowledge_points?.[0]?.topic1_name
        || item.question.knowledge_point?.split(/[\n,，;；/]+/).map((value) => value.trim()).find(Boolean)
        || '课堂练习';
      if (knowledge !== previousKnowledge) {
        const card = findKnowledgeCard(knowledge);
        if (card && !existingKnowledgeIds.has(card.id) && !existingCanonicalIds.has(card.id)) {
          items.push({
            type: 'knowledge',
            id: `knowledge-${card.id}`,
            knowledgeId: card.id,
            title: card.title,
            summary: card.summary,
            points: pointsForCard(card.points),
          });
          existingKnowledgeIds.add(card.id);
          existingCanonicalIds.add(card.id);
        }
        previousKnowledge = knowledge;
      }
      items.push(item);
      return items;
    }, []);
    commitItems(next, -1);
  }, [commitItems, composeItems, incomingTemplateConfig?.knowledge_length]);

  const handleBuildTeachingBlueprint = useCallback(() => {
    const questionItems = composeItems.filter((item): item is Extract<ComposeItem, { type: 'question' }> => item.type === 'question' && Boolean(item.question));
    if (questionItems.length === 0) return;

    const headerItems = composeItems.filter((item) => item.type === 'text' && (item.blockKind === 'exam_title' || item.blockKind === 'name_line'));
    const appendixItems = composeItems.filter((item) => item.type === 'text'
      && item.blockKind !== 'section_title'
      && !headerItems.some((header) => header.id === item.id));
    const groups = new Map<string, Array<Extract<ComposeItem, { type: 'question' }>>>();
    questionItems.forEach((item) => {
      const key = getPrimaryKnowledge(item.question!);
      groups.set(key, [...(groups.get(key) || []), item]);
    });
    const cards = buildKnowledgeCards(questionItems.map((item) => item.question!));
    const cardByTitle = new Map(cards.map((card) => [card.title, card]));
    const next: ComposeItem[] = [...headerItems];
    const previewGroups: TeachingBlueprintPreview['groups'] = [];
    [...groups.entries()].sort(([left], [right]) => left.localeCompare(right, 'zh-CN')).forEach(([knowledge, items], groupIndex) => {
      const card = cardByTitle.get(knowledge) || cards.find((candidate) => knowledge.includes(candidate.title) || candidate.title.includes(knowledge));
      const difficulties = items.map((item) => Number(item.question?.difficulty || 0)).filter(Boolean);
      previewGroups.push({
        knowledge,
        questionCount: items.length,
        difficultyRange: difficulties.length > 0 ? `${Math.min(...difficulties)} - ${Math.max(...difficulties)}` : '未标注',
      });
      next.push({
        type: 'text',
        id: makeId('section'),
        title: `${groupIndex + 1}. ${knowledge}`,
        content: `${groupIndex + 1}. ${knowledge}`,
        blockKind: 'section_title',
        style: { fontFamily: styleConfig.fontFamily, fontSize: 16, fontWeight: 'bold', textAlign: 'left' },
      });
      if (card) next.push({
        type: 'knowledge',
        id: `knowledge-${card.id}`,
        knowledgeId: card.id,
        title: card.title,
        summary: card.summary,
        points: card.points,
      });
      next.push(...[...items].sort((left, right) => {
        const difficultyDelta = Number(left.question?.difficulty || 0) - Number(right.question?.difficulty || 0);
        return difficultyDelta || (left.question?.question_type || '').localeCompare(right.question?.question_type || '') || left.questionId.localeCompare(right.questionId);
      }));
    });
    const compliance: string[] = [];
    if (blueprintRules.targetQuestionCount > 0 && questionItems.length !== blueprintRules.targetQuestionCount) {
      compliance.push(`当前 ${questionItems.length} 题，与目标题数 ${blueprintRules.targetQuestionCount} 题不一致。`);
    }
    if (blueprintRules.maxQuestionsPerKnowledge > 0) {
      previewGroups.filter((group) => group.questionCount > blueprintRules.maxQuestionsPerKnowledge).forEach((group) => {
        compliance.push(`“${group.knowledge}”有 ${group.questionCount} 题，超过每知识点上限 ${blueprintRules.maxQuestionsPerKnowledge} 题。`);
      });
    }
    if (blueprintRules.requireComprehensiveQuestion && !questionItems.some((item) => ['calculation', 'experiment'].includes(item.question?.question_type || ''))) {
      compliance.push('规则要求至少包含 1 道计算或实验题，但当前题目中未发现。');
    }
    setBlueprintPreview({
      items: [...next, ...appendixItems],
      groups: previewGroups,
      preservedTextCount: headerItems.length + appendixItems.length,
      removedPageBreakCount: composeItems.filter((item) => item.type === 'separator').length,
      compliance,
    });
  }, [blueprintRules, composeItems, styleConfig.fontFamily]);

  const handleApplyTeachingBlueprint = useCallback(() => {
    if (!blueprintPreview) return;
    commitItems(blueprintPreview.items, 0);
    setBlueprintPreview(null);
  }, [blueprintPreview, commitItems]);

  const handleFindSupplementCandidates = useCallback(async () => {
    const existingQuestions = composeItems.filter((item): item is Extract<ComposeItem, { type: 'question' }> => item.type === 'question' && Boolean(item.question));
    const existingIds = new Set(existingQuestions.map((item) => item.questionId));
    const missingCount = Math.max(0, blueprintRules.targetQuestionCount - existingQuestions.length);
    const needsComprehensive = blueprintRules.requireComprehensiveQuestion
      && !existingQuestions.some((item) => ['calculation', 'experiment'].includes(item.question?.question_type || ''));
    setSupplementLoading(true);
    setSupplementError(null);
    setSupplementOpen(true);
    try {
      const result = await searchQuestions({ limit: 50, offset: 0, search_mode: 'browse' });
      const coveredKnowledge = new Set(existingQuestions.map((item) => getPrimaryKnowledge(item.question!)));
      const knowledgeCounts = new Map<string, number>();
      existingQuestions.forEach((item) => {
        const knowledge = getPrimaryKnowledge(item.question!);
        knowledgeCounts.set(knowledge, (knowledgeCounts.get(knowledge) || 0) + 1);
      });
      const preferredCount = Math.max(5, missingCount || (needsComprehensive ? 3 : 5));
      const candidates = result.items
        .filter((question) => !existingIds.has(question.question_id))
        .filter((question) => !needsComprehensive || ['calculation', 'experiment'].includes(question.question_type || ''))
        .filter((question) => blueprintRules.maxQuestionsPerKnowledge <= 0 || (knowledgeCounts.get(getPrimaryKnowledge(question)) || 0) < blueprintRules.maxQuestionsPerKnowledge)
        .sort((left, right) => {
          const leftCoverage = coveredKnowledge.has(getPrimaryKnowledge(left)) ? 1 : 0;
          const rightCoverage = coveredKnowledge.has(getPrimaryKnowledge(right)) ? 1 : 0;
          return leftCoverage - rightCoverage || Number(left.difficulty || 0) - Number(right.difficulty || 0) || left.question_id.localeCompare(right.question_id);
        })
        .slice(0, Math.min(12, preferredCount + 4));
      setSupplementCandidates(candidates);
      setSelectedSupplementIds(candidates.slice(0, preferredCount).map((question) => question.question_id));
    } catch (error) {
      setSupplementCandidates([]);
      setSelectedSupplementIds([]);
      setSupplementError(error instanceof Error ? error.message : '未能读取题库候选题。');
    } finally {
      setSupplementLoading(false);
    }
  }, [blueprintRules.maxQuestionsPerKnowledge, blueprintRules.requireComprehensiveQuestion, blueprintRules.targetQuestionCount, composeItems]);

  const handleAddSupplementCandidates = useCallback(() => {
    const selected = supplementCandidates.filter((question) => selectedSupplementIds.includes(question.question_id));
    if (selected.length === 0) return;
    const newItems: ComposeItem[] = selected.map((question) => ({
      type: 'question', id: question.question_id, questionId: question.question_id, question,
    }));
    commitItems([...composeItems, ...newItems], composeItems.length);
    setSupplementOpen(false);
  }, [commitItems, composeItems, selectedSupplementIds, supplementCandidates]);

  const applyOutputProfile = useCallback((profile: 'student' | 'teacher') => {
    setOutputProfile(profile);
    setShowAnswers(profile === 'teacher');
    setShowAnalysis(profile === 'teacher');
  }, []);

  const handleMoveSelection = useCallback((direction: -1 | 1) => {
    const selected = new Set(selectedItemIds.length > 0 ? selectedItemIds : selectedItem ? [selectedItem.id] : []);
    if (selected.size === 0) return;
    const next = [...composeItems];
    if (direction < 0) {
      for (let index = 1; index < next.length; index += 1) {
        if (selected.has(next[index].id) && !selected.has(next[index - 1].id)) {
          [next[index - 1], next[index]] = [next[index], next[index - 1]];
        }
      }
    } else {
      for (let index = next.length - 2; index >= 0; index -= 1) {
        if (selected.has(next[index].id) && !selected.has(next[index + 1].id)) {
          [next[index], next[index + 1]] = [next[index + 1], next[index]];
        }
      }
    }
    const primaryIndex = next.findIndex((item) => item.id === selectedItem?.id);
    commitItems(next, primaryIndex);
  }, [commitItems, composeItems, selectedItem, selectedItemIds]);

  const handleDuplicateSelection = useCallback(() => {
    const selected = new Set(selectedItemIds.length > 0 ? selectedItemIds : selectedItem ? [selectedItem.id] : []);
    const source = composeItems.filter((item) => selected.has(item.id));
    if (source.length === 0) return;
    const copies = source.map((item) => ({ ...item, id: makeId(`${item.type}-copy`) } as ComposeItem));
    const lastIndex = Math.max(...composeItems.map((item, index) => selected.has(item.id) ? index : -1));
    const next = [...composeItems];
    next.splice(lastIndex + 1, 0, ...copies);
    commitItems(next, lastIndex + 1);
    setSelectedItemIds(copies.map((item) => item.id));
  }, [commitItems, composeItems, selectedItem, selectedItemIds]);

  const handleDeleteSelection = useCallback(() => {
    const selected = new Set(selectedItemIds.length > 0 ? selectedItemIds : selectedItem ? [selectedItem.id] : []);
    if (selected.size === 0) return;
    for (const item of composeItems) {
      if (selected.has(item.id) && item.type === 'question') removeFromBasket(item.questionId);
    }
    commitItems(composeItems.filter((item) => !selected.has(item.id)), -1);
    setSelectedItemIds([]);
  }, [commitItems, composeItems, removeFromBasket, selectedItem, selectedItemIds]);

  const handleAutoLayout = useCallback(() => {
    const compacted: ComposeItem[] = [];
    for (const item of composeItems) {
      if (item.type === 'separator' && compacted.at(-1)?.type === 'separator') continue;
      if (item.type === 'question' && item.question) {
        compacted.push({
          ...item,
          question: {
            ...item.question,
            figures: (item.question.figures || []).map((figure) => ({
              ...figure,
              display_scale: Math.min(100, Math.max(25, Number(figure.display_scale ?? 60))),
              display_align: figure.display_align || 'center',
            })),
          },
        });
      } else {
        compacted.push(item);
      }
    }
    while (compacted.at(-1)?.type === 'separator') compacted.pop();
    commitItems(compacted, selectedIndex);
    setStyleConfig((current) => ({
      ...current,
      optionLayout: 'auto',
      keepQuestionTogether: true,
      keepFigureWithStem: true,
      startLongQuestionOnNewPage: true,
      pageFillPercent: 90,
    }));
  }, [commitItems, composeItems, selectedIndex, setStyleConfig]);

  const handleSaveCurrent = useCallback(() => {
    saveLessonPackageToLibrary(previewLessonPackage);
    setDraftSaveState('saved');
  }, [previewLessonPackage, setDraftSaveState]);

  const handleClearAll = useCallback(() => {
    if (!window.confirm(`确定清空全部 ${composeItems.length} 个内容对象吗？此操作可通过撤销恢复。`)) return;
    clearBasket();
    commitItems([], -1);
  }, [clearBasket, commitItems, composeItems.length]);

  const openLessonRoute = useCallback((path: '/handout' | '/slides' | '/classroom') => {
    if (path === '/handout') {
      saveLessonPackageToLibrary(previewLessonPackage);
    } else {
      saveCurrentLessonPackage(previewLessonPackage);
    }
    navigate(path);
  }, [navigate, previewLessonPackage]);

  const nudgeZoom = useCallback((delta: number) => {
    setZoomMode('manual');
    setDocumentZoom((prev) => Math.max(50, Math.min(125, prev + delta)));
  }, []);

  useEffect(() => {
    if (!editingItemId) return;
    const handler = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        cancelInlineEdit();
      } else if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') {
        event.preventDefault();
        finishInlineEdit();
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [cancelInlineEdit, editingItemId, finishInlineEdit]);

  // ── Keyboard shortcuts ──
  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if (isEditableTarget(event.target)) return;
      const key = event.key.toLowerCase();
      if ((event.ctrlKey || event.metaKey) && key === 'z' && !event.shiftKey) {
        event.preventDefault();
        undoWorkspace();
      } else if ((event.ctrlKey || event.metaKey) && (key === 'y' || (key === 'z' && event.shiftKey))) {
        event.preventDefault();
        redoWorkspace();
      } else if ((event.key === 'Delete' || event.key === 'Backspace') && selectedIndex >= 0) {
        event.preventDefault();
        handleDeleteSelection();
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [handleDeleteSelection, redoWorkspace, selectedIndex, undoWorkspace]);

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

  return (
    <div className="flex h-full flex-col overflow-hidden bg-[#f2f5f9]">
      {previewModel && (
        <div className="compose-print-document">
          <HandoutDocument items={previewModel.items} config={previewModel.config} />
        </div>
      )}

      {/* ── Header ── */}
      <header className="compose-workbench-ui flex h-11 shrink-0 items-center gap-3 border-b border-[#d4deea] bg-white px-4 shadow-[0_1px_3px_rgba(15,23,42,0.04)]">
        <div className="flex h-6 items-center rounded bg-[#2567b8] px-2.5 text-xs font-bold tracking-wide text-white shadow-sm">
          组卷工作台
        </div>

        <div className="ml-auto flex shrink-0 items-center gap-1.5">
          <IconButton title="撤销 (Ctrl+Z)" disabled={!canUndo} onClick={undoWorkspace}>
            <UndoIcon />
          </IconButton>
          <IconButton title="重做 (Ctrl+Y)" disabled={!canRedo} onClick={redoWorkspace}>
            <RedoIcon />
          </IconButton>

          <div className="mx-1 h-5 w-px bg-[var(--color-border)]" />

          <SaveStateDot state={draftSaveState} />

          <Button variant="ghost" size="sm" onClick={handleClearAll}>
            清空
          </Button>
          <Button variant="outline" size="sm" onClick={handleSaveCurrent}>
            保存项目
          </Button>
          <Button size="sm" onClick={() => openLessonRoute('/handout')}>
            进入讲义排版
          </Button>
        </div>
      </header>

      {/* ── Toolbar ── */}
      <div className="compose-workbench-ui flex h-10 shrink-0 items-center gap-1 overflow-x-auto border-b border-[#d4deea] bg-[#f8fafc] px-3 shadow-[inset_0_-1px_0_rgba(255,255,255,0.55)]">
        <ToolButton active={outlineOpen} onClick={() => setOutlineOpen((current) => !current)} title="显示或收起文档大纲">
          大纲
        </ToolButton>
        <InsertMenu
          onAddExamTitle={handleAddEditableExamTitle}
          onAddNameLine={handleAddEditableNameLine}
          onAddSectionTitle={handleAddEditableSectionTitle}
          onAddTextBlock={handleAddTextBlock}
          onAddTextBox={handleAddTextBox}
          onAddPageBreak={handleAddPageBreak}
        />

        <ToolButton onClick={handleOrganizeByKnowledge} title="按题目知识点插入完整讲授卡，可用 Ctrl+Z 撤销">
          插入知识讲解
        </ToolButton>

        <ToolButton onClick={() => setBlueprintRulesOpen(true)} title="设置题数、知识点上限与题型约束">
          组卷规则
        </ToolButton>

        <ToolButton onClick={() => void handleFindSupplementCandidates()} title="按当前规则从题库筛选补题候选，勾选后再加入">
          自动补题
        </ToolButton>

        <ToolButton onClick={handleBuildTeachingBlueprint} title="按知识点分组、按难度排序，并自动补全章节标题与知识讲解">
          智能组卷蓝图
        </ToolButton>

        <ToolButton onClick={handleAutoLayout} title="统一题图、清理重复分页并启用智能分页，可用 Ctrl+Z 撤销">
          自动整理
        </ToolButton>

        <ToolButton onClick={() => navigate('/templates?scope=compose')} title="管理并应用组卷模板">
          模板
        </ToolButton>

        <ToolDivider />

        <SegmentedControl
          options={[
            { value: 'student', label: '学生版' },
            { value: 'teacher', label: '教师版' },
          ]}
          value={outputProfile}
          onChange={applyOutputProfile}
        />

        <PillToggle active={showAnswers} onClick={() => setShowAnswers((prev) => !prev)}>
          答案
        </PillToggle>
        <PillToggle active={showAnalysis} onClick={() => setShowAnalysis((prev) => !prev)}>
          解析
        </PillToggle>

        <ToolDivider />

        <div className="flex items-center gap-0.5">
          <IconButton title="缩小" onClick={() => nudgeZoom(-10)}>
            −
          </IconButton>
          <button
            type="button"
            onClick={() => {
              setZoomMode('manual');
              setDocumentZoom(100);
            }}
            className="w-12 rounded px-1 py-1 text-center text-xs font-semibold tabular-nums text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-hover)]"
            title="恢复 100%"
          >
            {effectiveZoom}%
          </button>
          <IconButton title="放大" onClick={() => nudgeZoom(10)}>
            ＋
          </IconButton>
          <ToolButton active={zoomMode === 'fit-width'} onClick={() => setZoomMode('fit-width')}>
            适应宽度
          </ToolButton>
        </div>

        <ToolDivider />

        <ToolButton
          active={inspectorOpen}
          onClick={() => {
            setInspectorOpen((prev) => !prev);
            setInspectorTab('view');
          }}
          title="内容显示和组卷预检"
        >
          内容检查
        </ToolButton>

        <div className="ml-auto flex items-center gap-1 pl-2">
          <span className="px-1 text-[10px] font-semibold text-[#8295aa]">下一步</span>
          <ToolButton onClick={() => openLessonRoute('/handout')}>讲义排版</ToolButton>
          <ToolButton onClick={() => openLessonRoute('/slides')}>课件制作</ToolButton>
          <ToolButton onClick={() => openLessonRoute('/classroom')}>课堂授课</ToolButton>
        </div>
      </div>

      {/* ── Main workspace ── */}
      <div className="compose-workbench-ui relative flex min-h-0 flex-1">
        {/* Collapsible document outline */}
        {outlineOpen && <aside className="relative flex w-[260px] shrink-0 flex-col border-r border-[#d4deea] bg-[#f8fafc]">
          <div className="flex min-h-12 shrink-0 items-center justify-between gap-2 border-b border-[#dbe4ef] bg-white px-2.5 py-2">
            <div className="flex rounded-md bg-[#edf2f7] p-0.5" role="tablist" aria-label="大纲视图">
              <button type="button" role="tab" aria-selected={outlineMode === 'content'} onClick={() => setOutlineMode('content')} className={`rounded px-2.5 py-1 text-[10px] font-semibold ${outlineMode === 'content' ? 'bg-white text-[#2567b8] shadow-sm' : 'text-[#71849a]'}`}>内容</button>
              <button type="button" role="tab" aria-selected={outlineMode === 'pages'} onClick={() => setOutlineMode('pages')} className={`rounded px-2.5 py-1 text-[10px] font-semibold ${outlineMode === 'pages' ? 'bg-white text-[#2567b8] shadow-sm' : 'text-[#71849a]'}`}>页面</button>
            </div>
            <button type="button" className="rounded px-1.5 py-1 text-xs text-[#8294a8] hover:bg-[#eef3f8]" onClick={() => setOutlineOpen(false)} title="收起大纲">✕</button>
          </div>
          <nav className="min-h-0 flex-1 overflow-hidden p-2" aria-label="试卷大纲">
            {outlineMode === 'content' && composeItems.length > 0 && <Virtuoso
              data={composeItems}
              className="h-full"
              increaseViewportBy={{ top: 300, bottom: 520 }}
              itemContent={(index, item) => {
              const typeLabel = item.type === 'question' ? formatQuestionType(item.question?.question_type || '') : item.type === 'text' ? '文本' : item.type === 'knowledge' ? '知识讲解' : '分页';
              const title = item.type === 'question' ? item.question?.title || item.questionId : item.title;
              const sourceLabel = item.type === 'question' ? getQuestionSourceLabel(item.question, '未标注来源') : '';
              return <div className="pb-1"><button
                key={item.id}
                type="button"
                onClick={(event) => selectCanvasItem(item.id, event.ctrlKey || event.metaKey)}
                onDoubleClick={() => editCanvasItem(item.id)}
                className={`grid w-full grid-cols-[24px_minmax(0,1fr)_28px] items-center gap-1 rounded-md border px-1.5 py-2 text-left transition-colors ${selectedItemIds.includes(item.id) || (selectedItemIds.length === 0 && selectedIndex === index) ? 'border-[#65a0dc] bg-white shadow-sm' : 'border-transparent bg-transparent hover:border-[#d5e0eb] hover:bg-white'}`}
              >
                <span className="flex h-5 w-5 items-center justify-center rounded bg-[#e8f1fb] text-[9px] font-bold text-[#2768ad]">{index + 1}</span>
                <span className="min-w-0"><strong className="block truncate text-[10px] text-[#405873]">{title}</strong><small className="block truncate text-[9px] text-[#91a2b5]" title={sourceLabel || typeLabel}>{typeLabel}{sourceLabel ? ` · ${sourceLabel}` : ''}</small></span>
                <span className="text-center text-[10px] text-[#7990a8]" title="双击编辑">编辑</span>
              </button></div>;
            }}
            />}
            {outlineMode === 'pages' && <div className="h-full space-y-1 overflow-y-auto">{measuredPages.map((page) => {
              const firstItem = composeItems.find((item) => item.id === page.itemIds[0]);
              const questionTotal = page.itemIds.filter((id) => composeItems.find((item) => item.id === id)?.type === 'question').length;
              return (
                <button key={page.index} type="button" onClick={() => page.itemIds[0] && locateItem(page.itemIds[0])} className="w-full rounded-md border border-[#d8e2ed] bg-white p-2 text-left shadow-sm transition hover:border-[#69a0d7]">
                  <div className="mb-2 flex items-center justify-between">
                    <strong className="text-[11px] text-[#34516f]">第 {page.index + 1} 页</strong>
                    <span className={`rounded px-1.5 py-0.5 text-[9px] ${page.usedPercent >= 100 ? 'bg-[#fff0f0] text-[#c23b3b]' : page.usedPercent >= 92 ? 'bg-[#fff7e6] text-[#a76400]' : 'bg-[#edf6ff] text-[#3874ad]'}`}>{page.usedPercent}%</span>
                  </div>
                  <div
                    className="mb-2 overflow-hidden border border-[#dce4ed] bg-white px-2 py-2 shadow-[0_2px_7px_rgba(15,23,42,0.08)]"
                    style={{ aspectRatio: styleConfig.pageOrientation === 'landscape' ? '297 / 210' : '210 / 297' }}
                    aria-label={`第 ${page.index + 1} 页缩略预览`}
                  >
                    <div className="mb-1.5 h-1.5 w-1/2 rounded-sm bg-[#30465f] opacity-80" />
                    <div className="space-y-1">
                      {page.itemIds.slice(0, 8).map((itemId) => {
                        const item = composeItems.find((candidate) => candidate.id === itemId);
                        const text = item?.type === 'question' ? item.question?.title || item.questionId : item?.title || '';
                        return (
                          <div key={itemId} className="flex items-start gap-1">
                            <span className={`mt-0.5 block h-1 w-1 shrink-0 rounded-full ${item?.type === 'question' ? 'bg-[#4d8fd1]' : item?.type === 'knowledge' ? 'bg-[#22a06b]' : 'bg-[#94a3b8]'}`} />
                            <span className="line-clamp-2 text-[6px] leading-[9px] text-[#60758a]">{text}</span>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                  <div className="h-1.5 overflow-hidden rounded-full bg-[#e8eef5]"><span className={`block h-full rounded-full ${page.usedPercent >= 100 ? 'bg-[#d94a4a]' : page.usedPercent >= 92 ? 'bg-[#e6a23c]' : 'bg-[#4d8fd1]'}`} style={{ width: `${Math.min(100, page.usedPercent)}%` }} /></div>
                  <div className="mt-2 truncate text-[9px] text-[#8295aa]">{questionTotal} 题 · {page.itemIds.length} 个对象{firstItem ? ` · ${firstItem.type === 'question' ? firstItem.question?.title || firstItem.questionId : firstItem.title}` : ''}</div>
                </button>
              );
            })}</div>}
            {composeItems.length === 0 && <div className="px-3 py-10 text-center text-[10px] leading-5 text-[#91a2b5]">从题篮加入题目，或使用顶部“插入”添加内容。</div>}
            {outlineMode === 'pages' && composeItems.length > 0 && measuredPages.length === 0 && <div className="px-3 py-10 text-center text-[10px] leading-5 text-[#91a2b5]">正在按白纸真实高度计算页面…</div>}
          </nav>
          <div className="shrink-0 border-t border-[#dbe4ef] bg-white px-3 py-2 text-[9px] text-[#8ca0b7]">{outlineMode === 'pages' ? `${effectivePaginationReport?.estimatedPageCount || 0} 页 · 按实际高度校准` : `${composeItems.length} 个对象 · 双击编辑`}</div>
        </aside>}

        {/* Canvas */}
        <main className="relative flex min-w-0 flex-1 flex-col bg-[#d9e2ed]">
          <div ref={documentCanvasRef} className="min-h-0 flex-1 overflow-auto">
            {!previewModel ? (
              <div className="flex h-[680px] items-center justify-center text-[var(--color-text-subtle)]">
                暂无可预览内容
              </div>
            ) : previewMode === 'A4' ? (
              <div className="flex justify-center px-5 py-4">
                <div style={{ zoom: effectiveZoom / 100 } as CSSProperties}>
                  <PageRuler styleConfig={styleConfig} pagesPerRow={documentPagesPerRow} pageGapMm={SPREAD_GAP_MM}>
                    <DndContext sensors={dndSensors} collisionDetection={closestCenter} onDragEnd={handleCanvasDragEnd}>
                      <SortableContext items={composeItems.map((item) => item.id)} strategy={verticalListSortingStrategy}>
                        <HandoutDocument
                          items={previewModel.items}
                          config={previewModel.config}
                          paginationEngine="estimated"
                          screenPagesPerRow={documentPagesPerRow}
                          screenCompact
                          screenPageLimit={renderAllPreviewPages ? undefined : screenPreviewPageLimit}
                          selectedItemId={selectedItem?.id}
                          selectedItemIds={selectedItemIds}
                          editingItemId={editingItemId}
                          onItemSelect={selectCanvasItem}
                          onItemEdit={editCanvasItem}
                          sortable={!editingItemId}
                          renderItemActions={(itemId) => itemId === selectedItem?.id ? (
                            <div className="pv-canvas-actions" role="toolbar" aria-label="内容操作">
                              {selectedItemIds.length > 1 && <span>{selectedItemIds.length} 项</span>}
                              <button type="button" title="上移" aria-label="上移" onClick={(event) => { event.stopPropagation(); handleMoveSelection(-1); }}><ArrowUp size={13} /></button>
                              <button type="button" title="下移" aria-label="下移" onClick={(event) => { event.stopPropagation(); handleMoveSelection(1); }}><ArrowDown size={13} /></button>
                              <button type="button" title="复制" aria-label="复制" onClick={(event) => { event.stopPropagation(); handleDuplicateSelection(); }}><Copy size={13} /></button>
                              <button type="button" title="在后面分页" aria-label="在后面分页" onClick={(event) => { event.stopPropagation(); handleAddPageBreak(); }}><Files size={13} /></button>
                              <button type="button" title="删除" aria-label="删除" onClick={(event) => { event.stopPropagation(); handleDeleteSelection(); }}><Trash2 size={13} /></button>
                            </div>
                          ) : null}
                          renderItemEditor={() => selectedItem ? (
                            <div className="pv-inline-editor" onClick={(event) => event.stopPropagation()} onDoubleClick={(event) => event.stopPropagation()}>
                              <div className="mb-3 flex items-center justify-between gap-3 border-b border-[#dce5ef] pb-2">
                                <strong className="text-xs text-[#294764]">正在原位编辑</strong>
                                <div className="flex gap-2">
                                  <button type="button" onClick={cancelInlineEdit} className="rounded border border-[#cfdbe8] bg-white px-3 py-1.5 text-xs font-semibold text-[#60778f]">取消</button>
                                  <button type="button" onClick={finishInlineEdit} className="rounded bg-[#2567b8] px-3 py-1.5 text-xs font-semibold text-white">保存</button>
                                </div>
                              </div>
                              {selectedItem.type === 'question' && selectedItem.question ? (
                                <QuestionLiveEditor question={selectedItem.question} onChange={updateSelectedQuestion} compact showPreview={false} showHeader={false} />
                              ) : (
                                <ObjectItemEditor
                                  item={selectedItem}
                                  fallbackFontFamily={styleConfig.fontFamily}
                                  fallbackFontSize={styleConfig.fontSize}
                                  onChangeItem={updateSelectedItem}
                                  onChangeQuestion={updateSelectedQuestion}
                                  onChangeText={updateSelectedTextItem}
                                />
                              )}
                            </div>
                          ) : null}
                        />
                      </SortableContext>
                    </DndContext>
                  </PageRuler>
                </div>
              </div>
            ) : (
              <div className="space-y-5 px-6 py-5">
                {slideDeck.pages.slice(0, 5).map((page) => (
                  <div
                    key={page.id}
                    className="mx-auto flex max-w-[980px] flex-col overflow-hidden rounded-lg border border-[var(--color-border)] bg-white shadow-[var(--shadow-lg)]"
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

        </main>

        {/* Inspector */}
        {inspectorOpen && (
          <aside className="compose-inspector relative z-10 flex w-[min(440px,42vw)] min-w-[340px] shrink-0 flex-col border-l border-[#d4deea] bg-[#f6f8fb] shadow-[-14px_0_30px_rgba(15,23,42,0.16)]">
            <div className="compose-inspector__tabs flex min-h-14 shrink-0 items-center gap-1 overflow-x-auto border-b border-[#dbe4ef] bg-white px-3">
              {(
                [
                  ['view', '显示'],
                  ['preflight', '预检'],
                  ...(selectedItem ? [['object', '当前对象'] as const] : []),
                ] as Array<readonly [typeof inspectorTab, string]>
              ).map(([tab, label]) => (
                <button
                  key={tab}
                  type="button"
                  onClick={() => setInspectorTab(tab)}
                    className={`min-w-[54px] shrink-0 whitespace-nowrap rounded-md px-2 py-2.5 text-[11px] font-semibold transition-colors ${
                    inspectorTab === tab
                      ? 'bg-[#e8f1fb] text-[#1f5fb8] shadow-[inset_0_0_0_1px_rgba(37,103,184,0.10)]'
                      : 'text-[var(--color-text-muted)] hover:bg-white hover:text-[var(--color-text)]'
                  }`}
                >
                  {label}
                </button>
              ))}
              <button
                type="button"
                onClick={() => setInspectorOpen(false)}
                className="ml-auto rounded px-1.5 py-1 text-xs text-[var(--color-text-subtle)] hover:bg-white hover:text-[var(--color-text)]"
                title="收起面板"
              >
                ✕
              </button>
            </div>

            <div className="min-h-0 flex-1 overflow-y-auto p-4">
              {inspectorTab === 'view' && (
                <PanelCard title="组卷页只负责内容">
                  <div className="space-y-3 text-xs leading-5 text-[#60778f]">
                    <p>题目、知识讲解、文本块和分页顺序在这里编辑。纸张、页边距、页眉页脚与最终分页请到讲义排版页设置。</p>
                    <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
                      <button type="button" onClick={() => openLessonRoute('/handout')} className="rounded-md border border-[#c9dced] bg-white px-3 py-2 text-left font-semibold text-[#2567b8] hover:bg-[#f2f7fc]">讲义排版</button>
                      <button type="button" onClick={() => openLessonRoute('/slides')} className="rounded-md border border-[#c9dced] bg-white px-3 py-2 text-left font-semibold text-[#2567b8] hover:bg-[#f2f7fc]">课件制作</button>
                      <button type="button" onClick={() => openLessonRoute('/classroom')} className="rounded-md border border-[#c9dced] bg-white px-3 py-2 text-left font-semibold text-[#2567b8] hover:bg-[#f2f7fc]">课堂授课</button>
                    </div>
                    <ToggleRow label="显示答案" active={showAnswers} onClick={() => setShowAnswers((prev) => !prev)} />
                    <ToggleRow label="显示解析" active={showAnalysis} onClick={() => setShowAnalysis((prev) => !prev)} />
                    <div className="rounded-lg bg-[var(--color-bg-hover)] px-3 py-2">
                      <Select
                        label="导出答案安排"
                        size="sm"
                        value={answerExportMode}
                        options={ANSWER_EXPORT_OPTIONS}
                        onChange={(event) => setAnswerExportMode(event.target.value as AnswerExportMode)}
                      />
                    </div>
                    <ToggleRow label="渲染全部页面" active={renderAllPreviewPages} onClick={() => setRenderAllPreviewPages((prev) => !prev)} />
                  </div>
                </PanelCard>
              )}

              {inspectorTab === 'preflight' && (
                <PreflightSection
                  report={diagnostics}
                  questionCount={questionCount}
                  pageBreakCount={pageBreakCount}
                  saveState={draftSaveState}
                  paginationReport={effectivePaginationReport}
                  onLocateQuestion={locateQuestion}
                  onFixWarning={fixDiagnosticWarning}
                />
              )}

              {inspectorTab === 'object' && selectedItem && (
                <PanelCard title="当前对象">
                  <div className="space-y-3">
                    <div className="rounded-md bg-[#f2f6fa] px-3 py-2">
                      <div className="text-[10px] font-semibold text-[#38516c]">{selectedItem.type === 'question' ? '题目' : selectedItem.type === 'knowledge' ? '知识讲解' : selectedItem.type === 'text' ? '文本' : '分页符'}</div>
                      <div className="mt-1 line-clamp-3 text-[10px] leading-5 text-[#71849a]">{selectedItem.type === 'question' ? selectedItem.question?.title || selectedItem.questionId : selectedItem.title}</div>
                    </div>
                    <button type="button" onClick={() => editCanvasItem(selectedItem.id)} className="h-9 w-full rounded-md bg-[#2567b8] text-xs font-semibold text-white hover:bg-[#1e579c]">原位编辑</button>
                    <div className="text-[9px] leading-4 text-[#91a2b5]">也可以在白纸上双击当前内容。</div>
                  </div>
                </PanelCard>
              )}
            </div>
          </aside>
        )}

      </div>

      {/* ── Status bar ── */}
      <div className="compose-workbench-ui">
      <StatusBar
        selectedItem={selectedItem}
        questionCount={questionCount}
        knowledgeCount={knowledgeCount}
        textCount={textCount}
        pageBreakCount={pageBreakCount}
        totalScore={diagnostics.totalScore}
        riskCount={diagnostics.warnings.filter((warning) => warning.level === 'danger').length}
        warningCount={diagnostics.warnings.filter((warning) => warning.level === 'warning').length}
        saveState={draftSaveState}
        zoom={effectiveZoom}
        layoutLabel={documentLayoutLabel}
      />
      </div>
      {blueprintPreview && <TeachingBlueprintDialog
        preview={blueprintPreview}
        onClose={() => setBlueprintPreview(null)}
        onApply={handleApplyTeachingBlueprint}
      />}
      {blueprintRulesOpen && <TeachingBlueprintRulesDialog
        rules={blueprintRules}
        onChange={setBlueprintRules}
        onClose={() => setBlueprintRulesOpen(false)}
      />}
      {supplementOpen && <SupplementCandidatesDialog
        candidates={supplementCandidates}
        selectedIds={selectedSupplementIds}
        loading={supplementLoading}
        error={supplementError}
        onToggle={(questionId) => setSelectedSupplementIds((current) => current.includes(questionId) ? current.filter((id) => id !== questionId) : [...current, questionId])}
        onClose={() => setSupplementOpen(false)}
        onApply={handleAddSupplementCandidates}
      />}
    </div>
  );
}

/* ═══════════════ Toolbar primitives ═══════════════ */

function SupplementCandidatesDialog({ candidates, selectedIds, loading, error, onToggle, onClose, onApply }: {
  candidates: Question[];
  selectedIds: string[];
  loading: boolean;
  error: string | null;
  onToggle: (questionId: string) => void;
  onClose: () => void;
  onApply: () => void;
}) {
  return (
    <div className="fixed inset-0 z-[75] flex items-center justify-center bg-slate-900/30 p-4" role="dialog" aria-modal="true" aria-label="智能补题候选">
      <section className="flex max-h-[82vh] w-full max-w-2xl flex-col overflow-hidden rounded-xl border border-[#cbdbea] bg-white shadow-2xl">
        <header className="border-b border-[#dce6f0] bg-[#f7fbff] px-5 py-4">
          <h2 className="text-base font-bold text-[#183a60]">智能补题候选</h2>
          <p className="mt-1 text-xs text-[#66809a]">依据当前题数、知识覆盖和综合题规则筛选，确认后才会加入试卷。</p>
        </header>
        <div className="min-h-0 flex-1 overflow-y-auto p-4">
          {loading && <div className="py-12 text-center text-sm text-[#71849a]">正在从题库筛选候选题…</div>}
          {error && <div className="rounded-lg bg-[#fff2f2] px-3 py-2 text-xs text-[#b43b3b]">{error}</div>}
          {!loading && !error && <div className="space-y-2">
            {candidates.map((question) => (
              <label key={question.question_id} className={`flex cursor-pointer items-start gap-3 rounded-lg border p-3 ${selectedIds.includes(question.question_id) ? 'border-[#66a0d8] bg-[#f3f8fd]' : 'border-[#dde6ef] bg-white hover:border-[#a8bfd5]'}`}>
                <input type="checkbox" checked={selectedIds.includes(question.question_id)} onChange={() => onToggle(question.question_id)} className="mt-0.5 h-4 w-4 accent-[#2567b8]" />
                <span className="min-w-0 flex-1">
                  <strong className="block line-clamp-2 text-xs leading-5 text-[#2d4964]">{question.title || question.stem_text || question.question_id}</strong>
                  <small className="mt-1 block text-[10px] text-[#7d91a5]">{formatQuestionType(question.question_type || '')} · 难度 {question.difficulty || '未标注'} · {getPrimaryKnowledge(question)}</small>
                </span>
              </label>
            ))}
            {candidates.length === 0 && <div className="py-12 text-center text-sm text-[#71849a]">当前规则下没有合适的候选题。</div>}
          </div>}
        </div>
        <footer className="flex items-center justify-between border-t border-[#dce6f0] bg-[#fbfdff] px-5 py-3">
          <span className="text-xs text-[#71849a]">已选 {selectedIds.length} 题</span>
          <div className="flex gap-2"><button type="button" onClick={onClose} className="rounded-lg border border-[#cfdeeb] px-3 py-2 text-xs font-semibold text-[#57718b]">取消</button><button type="button" disabled={selectedIds.length === 0 || loading} onClick={onApply} className="rounded-lg bg-[#2567b8] px-3 py-2 text-xs font-semibold text-white disabled:opacity-45">加入试卷</button></div>
        </footer>
      </section>
    </div>
  );
}

function TeachingBlueprintDialog({
  preview,
  onClose,
  onApply,
}: {
  preview: TeachingBlueprintPreview;
  onClose: () => void;
  onApply: () => void;
}) {
  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center bg-slate-900/25 p-4" role="dialog" aria-modal="true" aria-label="智能组卷蓝图预览">
      <section className="w-full max-w-lg overflow-hidden rounded-2xl border border-[#cbdced] bg-white shadow-2xl">
        <header className="border-b border-[#dce6f0] bg-[#f7fbff] px-5 py-4">
          <h2 className="text-base font-bold text-[#183a60]">智能组卷蓝图预览</h2>
          <p className="mt-1 text-xs leading-5 text-[#66809a]">确认后将按知识点分章，并在每章内按难度递进排列题目。</p>
        </header>
        <div className="space-y-4 px-5 py-4">
          <div className="grid grid-cols-3 gap-2">
            <BlueprintMetric label="知识模块" value={preview.groups.length} />
            <BlueprintMetric label="生成对象" value={preview.items.length} />
            <BlueprintMetric label="保留文本" value={preview.preservedTextCount} />
          </div>
          <div className="rounded-xl border border-[#d9e6f3]">
            <div className="border-b border-[#e3edf6] px-3 py-2 text-xs font-semibold text-[#456886]">组卷结构</div>
            <div className="max-h-56 divide-y divide-[#edf2f7] overflow-y-auto">
              {preview.groups.map((group, index) => <div key={group.knowledge} className="flex items-center justify-between gap-3 px-3 py-2.5 text-xs"><div className="min-w-0"><span className="mr-2 font-bold text-[#2a70b8]">{index + 1}</span><span className="font-medium text-[#294966]">{group.knowledge}</span></div><span className="shrink-0 text-[#71879d]">{group.questionCount} 题 · 难度 {group.difficultyRange}</span></div>)}
            </div>
          </div>
          {preview.removedPageBreakCount > 0 && <div className="rounded-lg bg-[#fff8e8] px-3 py-2 text-xs leading-5 text-[#9b6916]">将重新计算分页，原有 {preview.removedPageBreakCount} 个手动分页符不会保留。</div>}
          {preview.compliance.length > 0 ? <div className="rounded-lg bg-[#fff4f4] px-3 py-2 text-xs leading-5 text-[#b43b3b]"><div className="font-semibold">规则待满足</div><ul className="mt-1 list-disc space-y-0.5 pl-4">{preview.compliance.map((issue) => <li key={issue}>{issue}</li>)}</ul></div> : <div className="rounded-lg bg-[#eefaf4] px-3 py-2 text-xs leading-5 text-[#26805d]">已符合当前组卷规则。</div>}
          <div className="rounded-lg bg-[#f1f8ff] px-3 py-2 text-xs leading-5 text-[#477294]">应用后仍可使用 Ctrl+Z 恢复到当前结构。</div>
        </div>
        <footer className="flex justify-end gap-2 border-t border-[#dce6f0] bg-[#fbfdff] px-5 py-3">
          <button type="button" onClick={onClose} className="rounded-lg border border-[#cfdeeb] px-3 py-2 text-xs font-semibold text-[#57718b] hover:bg-white">返回修改</button>
          <button type="button" onClick={onApply} className="rounded-lg bg-[#2567b8] px-3 py-2 text-xs font-semibold text-white shadow-sm hover:bg-[#1e5a9f]">应用蓝图</button>
        </footer>
      </section>
    </div>
  );
}

function BlueprintMetric({ label, value }: { label: string; value: number }) {
  return <div className="rounded-lg bg-[#edf5fd] px-2 py-2 text-center"><div className="text-lg font-black text-[#2268ae]">{value}</div><div className="text-[10px] text-[#66809a]">{label}</div></div>;
}

function TeachingBlueprintRulesDialog({
  rules,
  onChange,
  onClose,
}: {
  rules: TeachingBlueprintRules;
  onChange: (rules: TeachingBlueprintRules) => void;
  onClose: () => void;
}) {
  const setNumber = (key: 'targetQuestionCount' | 'maxQuestionsPerKnowledge', value: string) => {
    onChange({ ...rules, [key]: Math.max(0, Number(value) || 0) });
  };
  return (
    <div className="fixed inset-0 z-[71] flex items-center justify-center bg-slate-900/25 p-4" role="dialog" aria-modal="true" aria-label="组卷规则">
      <section className="w-full max-w-md overflow-hidden rounded-2xl border border-[#cbdced] bg-white shadow-2xl">
        <header className="border-b border-[#dce6f0] bg-[#f7fbff] px-5 py-4"><h2 className="text-base font-bold text-[#183a60]">组卷规则</h2><p className="mt-1 text-xs leading-5 text-[#66809a]">未填写的限制不会参与检查，规则会在蓝图预览中验证。</p></header>
        <div className="space-y-4 px-5 py-4 text-sm text-[#395b78]">
          <label className="block"><span className="mb-1.5 block text-xs font-semibold">目标题数 <em className="font-normal text-[#8ca0b3]">0 表示不限制</em></span><input type="number" min="0" value={rules.targetQuestionCount || ''} onChange={(event) => setNumber('targetQuestionCount', event.target.value)} placeholder="例如：20" className="h-10 w-full rounded-lg border border-[#c9dbea] px-3 outline-none focus:border-[#4a89cf]" /></label>
          <label className="block"><span className="mb-1.5 block text-xs font-semibold">单个知识点最多题数 <em className="font-normal text-[#8ca0b3]">0 表示不限制</em></span><input type="number" min="0" value={rules.maxQuestionsPerKnowledge || ''} onChange={(event) => setNumber('maxQuestionsPerKnowledge', event.target.value)} placeholder="例如：5" className="h-10 w-full rounded-lg border border-[#c9dbea] px-3 outline-none focus:border-[#4a89cf]" /></label>
          <label className="flex cursor-pointer items-start gap-2 rounded-lg bg-[#f5faff] p-3 text-xs leading-5"><input type="checkbox" checked={rules.requireComprehensiveQuestion} onChange={(event) => onChange({ ...rules, requireComprehensiveQuestion: event.target.checked })} className="mt-0.5 h-4 w-4 accent-[#2567b8]" /><span><strong className="block text-[#315a80]">至少包含 1 道计算或实验题</strong><span className="text-[#6c88a2]">适合综合训练或阶段测试。</span></span></label>
        </div>
        <footer className="flex justify-end border-t border-[#dce6f0] bg-[#fbfdff] px-5 py-3"><button type="button" onClick={onClose} className="rounded-lg bg-[#2567b8] px-3 py-2 text-xs font-semibold text-white shadow-sm hover:bg-[#1e5a9f]">保存规则</button></footer>
      </section>
    </div>
  );
}

function ToolDivider() {
  return <div className="mx-1.5 h-5 w-px shrink-0 bg-[#d4deea]" />;
}

function ToolButton({
  active,
  children,
  onClick,
  title,
  disabled,
}: {
  active?: boolean;
  children: React.ReactNode;
  onClick?: () => void;
  title?: string;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={title}
      disabled={disabled}
      aria-pressed={active || undefined}
      className={`h-7 shrink-0 rounded px-2.5 text-xs font-semibold transition-colors ${
        active
          ? 'bg-[#e8f1fb] text-[#1f5fb8] shadow-[inset_0_0_0_1px_rgba(37,103,184,0.12)]'
          : 'text-[var(--color-text-secondary)] hover:bg-white hover:text-[var(--color-text)] hover:shadow-sm'
      } disabled:cursor-not-allowed disabled:opacity-35`}
    >
      {children}
    </button>
  );
}

function IconButton({
  children,
  onClick,
  title,
  disabled,
}: {
  children: React.ReactNode;
  onClick?: () => void;
  title?: string;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={title}
      disabled={disabled}
      className="flex h-7 w-7 shrink-0 items-center justify-center rounded text-[var(--color-text-secondary)] transition-colors hover:bg-white hover:text-[var(--color-text)] hover:shadow-sm disabled:cursor-not-allowed disabled:opacity-35"
    >
      {children}
    </button>
  );
}

function SegmentedControl<T extends string>({
  options,
  value,
  onChange,
}: {
  options: Array<{ value: T; label: string }>;
  value: T;
  onChange: (value: T) => void;
}) {
  return (
    <div className="flex shrink-0 items-center rounded bg-[#e8eef6] p-0.5 ring-1 ring-[#d7e0eb]">
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          onClick={() => onChange(option.value)}
          className={`h-6 rounded px-2.5 text-xs font-semibold transition-colors ${
            value === option.value
              ? 'bg-white text-[#1f5fb8] shadow-sm'
              : 'text-[var(--color-text-muted)] hover:text-[var(--color-text)]'
          }`}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}

function PillToggle({
  active,
  children,
  onClick,
}: {
  active: boolean;
  children: React.ReactNode;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`flex h-7 shrink-0 items-center gap-1.5 rounded border px-2.5 text-xs font-semibold transition-colors ${
        active
          ? 'border-[#a9c8ef] bg-[#e8f1fb] text-[#1f5fb8]'
          : 'border-[#d4deea] bg-white/70 text-[var(--color-text-muted)] hover:border-[#bcc9d8] hover:text-[var(--color-text)]'
      }`}
    >
      <span
        className={`h-1.5 w-1.5 rounded-full ${active ? 'bg-[var(--color-accent)]' : 'bg-[var(--color-text-subtle)]'}`}
      />
      {children}
    </button>
  );
}

function InsertMenu({
  onAddExamTitle,
  onAddNameLine,
  onAddSectionTitle,
  onAddTextBlock,
  onAddTextBox,
  onAddPageBreak,
}: {
  onAddExamTitle: () => void;
  onAddNameLine: () => void;
  onAddSectionTitle: () => void;
  onAddTextBlock: () => void;
  onAddTextBox: () => void;
  onAddPageBreak: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [menuPosition, setMenuPosition] = useState<{ left: number; top: number } | null>(null);
  const rootRef = useRef<HTMLDivElement | null>(null);

  const updateMenuPosition = useCallback(() => {
    const rect = rootRef.current?.getBoundingClientRect();
    if (!rect) return;
    const menuWidth = 240;
    setMenuPosition({
      left: Math.max(8, Math.min(rect.left, window.innerWidth - menuWidth - 8)),
      top: rect.bottom + 6,
    });
  }, []);

  useEffect(() => {
    if (!open) return;
    const handler = (event: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [open]);

  useEffect(() => {
    if (!open) return;
    updateMenuPosition();
    window.addEventListener('resize', updateMenuPosition);
    window.addEventListener('scroll', updateMenuPosition, true);
    return () => {
      window.removeEventListener('resize', updateMenuPosition);
      window.removeEventListener('scroll', updateMenuPosition, true);
    };
  }, [open, updateMenuPosition]);

  const entries: Array<{ key: string; icon: string; label: string; hint: string; action: () => void }> = [
    { key: 'exam-title', icon: 'H1', label: '试卷大标题', hint: '居中大字号标题', action: onAddExamTitle },
    { key: 'name-line', icon: '☰', label: '姓名信息栏', hint: '班级 / 姓名 / 学号', action: onAddNameLine },
    { key: 'section', icon: '§', label: '试卷小标题', hint: '如"一、单项选择题"', action: onAddSectionTitle },
    { key: 'text-box', icon: '□', label: '文本框', hint: '带边框，可放提示或留空', action: onAddTextBox },
    { key: 'text', icon: '¶', label: '说明段落', hint: '导语、说明、过渡段', action: onAddTextBlock },
    { key: 'break', icon: '⏎', label: '分页符', hint: '强制另起一页', action: onAddPageBreak },
  ];

  return (
    <div ref={rootRef} className="relative shrink-0">
      <button
        type="button"
        onClick={() => {
          if (!open) updateMenuPosition();
          setOpen((prev) => !prev);
        }}
        className={`flex h-7 items-center gap-1 rounded px-2.5 text-xs font-semibold transition-colors ${
          open
            ? 'bg-[#e8f1fb] text-[#1f5fb8]'
            : 'text-[var(--color-text-secondary)] hover:bg-white hover:text-[var(--color-text)]'
        }`}
      >
        <span className="text-sm leading-none">＋</span>
        插入
        <svg className="h-2.5 w-2.5 opacity-60" viewBox="0 0 10 10" fill="none" stroke="currentColor" strokeWidth="1.5">
          <path d="M2 3.5l3 3 3-3" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>

      {open && (
        <div
          className="fixed z-[9999] w-[240px] overflow-hidden rounded-md border border-[#cbd7e6] bg-white p-1.5 shadow-[var(--shadow-xl)]"
          style={{
            left: menuPosition?.left ?? 12,
            top: menuPosition?.top ?? 84,
          }}
        >
          <div className="px-2 pb-1.5 pt-1 text-[10px] font-semibold tracking-wider text-[var(--color-text-subtle)]">
            插入到选中项之后
          </div>
          {entries.map((entry) => (
            <button
              key={entry.key}
              type="button"
              onClick={() => {
                entry.action();
                setOpen(false);
              }}
              className="flex w-full items-center gap-2.5 rounded px-2 py-2 text-left transition-colors hover:bg-[#e8f1fb]"
            >
              <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded bg-[#edf3f9] text-[11px] font-bold text-[var(--color-text-secondary)]">
                {entry.icon}
              </span>
              <span className="min-w-0">
                <span className="block text-xs font-semibold text-[var(--color-text-main)]">{entry.label}</span>
                <span className="block truncate text-[10px] text-[var(--color-text-muted)]">{entry.hint}</span>
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

/* ═══════════════ Header bits ═══════════════ */

function SaveStateDot({ state }: { state: 'idle' | 'saving' | 'saved' | 'error' }) {
  const meta = {
    idle: { color: 'var(--color-text-subtle)', label: '等待编辑' },
    saving: { color: 'var(--color-orange)', label: '保存中…' },
    saved: { color: 'var(--color-green)', label: '已自动保存' },
    error: { color: 'var(--color-danger)', label: '同步失败（本地已保留）' },
  }[state];

  return (
    <span className="flex items-center gap-1.5 px-1 text-[11px] text-[var(--color-text-muted)]" title={meta.label}>
      <span
        className={`h-1.5 w-1.5 rounded-full ${state === 'saving' ? 'animate-pulse' : ''}`}
        style={{ background: meta.color }}
      />
      {meta.label}
    </span>
  );
}

function UndoIcon() {
  return (
    <svg className="h-3.5 w-3.5" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6">
      <path d="M3 7h6a3.5 3.5 0 0 1 0 7H7" strokeLinecap="round" />
      <path d="M6 3.5L2.5 7 6 10.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function RedoIcon() {
  return (
    <svg className="h-3.5 w-3.5" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6">
      <path d="M13 7H7a3.5 3.5 0 0 0 0 7h2" strokeLinecap="round" />
      <path d="M10 3.5L13.5 7 10 10.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

/* ═══════════════ Inspector panels ═══════════════ */

function PanelCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-card)] p-3 shadow-[var(--shadow-sm)]">
      <div className="mb-2.5 text-xs font-semibold tracking-wide text-[var(--color-text-secondary)]">{title}</div>
      {children}
    </section>
  );
}

function ToggleRow({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex w-full items-center justify-between rounded-lg bg-[var(--color-bg-hover)] px-3 py-2 text-xs font-semibold text-[var(--color-text-secondary)] transition-colors hover:text-[var(--color-text)]"
    >
      <span>{label}</span>
      <span className={`h-4 w-8 rounded-full p-0.5 transition-colors ${active ? 'bg-[var(--color-accent)]' : 'bg-slate-300'}`}>
        <span className={`block h-3 w-3 rounded-full bg-white shadow transition-transform ${active ? 'translate-x-4' : ''}`} />
      </span>
    </button>
  );
}

function ObjectItemEditor({
  item,
  fallbackFontFamily,
  fallbackFontSize,
  onChangeItem,
  onChangeQuestion,
  onChangeText,
}: {
  item: ComposeItem;
  fallbackFontFamily: HandoutStyleConfig['fontFamily'];
  fallbackFontSize: number;
  onChangeItem: (updater: (item: ComposeItem) => ComposeItem) => void;
  onChangeQuestion: (patch: Partial<Question>) => void;
  onChangeText: (patch: Partial<ComposeTextItem>) => void;
}) {
  if (item.type === 'text') {
    return (
      <TextItemEditor
        item={item}
        fallbackFontFamily={fallbackFontFamily}
        fallbackFontSize={fallbackFontSize}
        onChange={onChangeText}
      />
    );
  }

  if (item.type === 'question') {
    const question = item.question;
    const options = question?.options || [];

    const updateOption = (index: number, value: string) => {
      if (!question) return;
      const next = [...options];
      next[index] = { ...next[index], content: value };
      onChangeQuestion({ options: next });
    };

    return (
      <div className="space-y-3">
        <PanelCard title="题目对象">
          {!question ? (
            <div className="rounded bg-[var(--color-bg-hover)] px-2.5 py-2 text-xs text-[var(--color-text-muted)]">
              题目尚未加载，暂时只能调整顺序。
            </div>
          ) : (
            <div className="space-y-3">
              <CompactEditorField label="题号">
                <input
                  value={question.question_id || item.questionId}
                  readOnly
                  className="h-7 w-full rounded border border-[var(--color-border)] bg-[var(--color-bg-hover)] px-2 text-xs text-[var(--color-text-muted)] outline-none"
                />
              </CompactEditorField>
              <CompactEditorField label="标题 / 题干">
                <StructuredTextEditor
                  value={question.title || ''}
                  onChange={(value) => onChangeQuestion({ title: value })}
                  placeholder="输入题干，支持标题、列表和重点标记"
                  minHeight={120}
                />
              </CompactEditorField>
              {options.length > 0 && (
                <CompactEditorField label="选项">
                  <div className="space-y-1.5">
                    {options.map((option, index) => (
                      <div key={`${option.opt}-${index}`} className="grid grid-cols-[24px_minmax(0,1fr)] gap-1.5">
                        <span className="flex h-7 items-center justify-center rounded bg-[var(--color-bg-hover)] text-[10px] font-bold text-[var(--color-accent)]">
                          {option.opt}
                        </span>
                        <input
                          value={option.content}
                          onChange={(event) => updateOption(index, event.target.value)}
                          className="h-7 min-w-0 rounded border border-[var(--color-border)] bg-white px-2 text-xs text-[var(--color-text)] outline-none focus:border-[var(--color-accent)]"
                        />
                      </div>
                    ))}
                  </div>
                </CompactEditorField>
              )}
              <div className="grid grid-cols-2 gap-2">
                <CompactEditorField label="答案">
                  <textarea
                    value={question.answer || ''}
                    onChange={(event) => onChangeQuestion({ answer: event.target.value })}
                    rows={3}
                    className="w-full resize-y rounded border border-[var(--color-border)] bg-white px-2 py-1.5 text-xs leading-5 text-[var(--color-text)] outline-none focus:border-[var(--color-accent)]"
                  />
                </CompactEditorField>
                <CompactEditorField label="难度">
                  <select
                    value={String(question.difficulty || 0)}
                    onChange={(event) => onChangeQuestion({ difficulty: Number(event.target.value) })}
                    className="h-7 w-full rounded border border-[var(--color-border)] bg-white px-2 text-xs text-[var(--color-text)] outline-none focus:border-[var(--color-accent)]"
                  >
                    <option value="0">未设</option>
                    <option value="1">1</option>
                    <option value="2">2</option>
                    <option value="3">3</option>
                    <option value="4">4</option>
                    <option value="5">5</option>
                  </select>
                </CompactEditorField>
              </div>
              <CompactEditorField label="解析">
                <StructuredTextEditor
                  value={question.analysis || ''}
                  onChange={(value) => onChangeQuestion({ analysis: value })}
                  placeholder="输入解题思路、步骤与结论"
                  minHeight={112}
                  compact
                />
              </CompactEditorField>
              <CompactEditorField label="来源">
                <input
                  value={question.source || ''}
                  onChange={(event) => onChangeQuestion({ source: event.target.value })}
                  className="h-7 w-full rounded border border-[var(--color-border)] bg-white px-2 text-xs text-[var(--color-text)] outline-none focus:border-[var(--color-accent)]"
                />
              </CompactEditorField>
            </div>
          )}
        </PanelCard>
      </div>
    );
  }

  if (item.type === 'knowledge') {
    // Older knowledge cards keep the overview and teaching points separately.
    // In the workbench they should be edited as one complete rich document.
    const knowledgeContent = [
      item.summary.trim(),
      ...item.points.map((point) => `- ${point}`),
    ].filter(Boolean).join('\n\n');

    return (
      <PanelCard title="知识讲解">
        <div className="space-y-3">
          <CompactEditorField label="标题">
            <input
              value={item.title}
              onChange={(event) => onChangeItem((current) => current.type === 'knowledge' ? { ...current, title: event.target.value } : current)}
              className="h-7 w-full rounded border border-[var(--color-border)] bg-white px-2 text-xs text-[var(--color-text)] outline-none focus:border-[var(--color-accent)]"
            />
          </CompactEditorField>
          <CompactEditorField label="知识点内容">
            <StructuredTextEditor
              value={knowledgeContent}
              onChange={(value) => onChangeItem((current) => current.type === 'knowledge' ? { ...current, summary: value, points: [] } : current)}
              placeholder="输入概念、条件或教学说明"
              minHeight={240}
              compact
            />
          </CompactEditorField>
        </div>
      </PanelCard>
    );
  }

  return (
    <PanelCard title="分页对象">
      <CompactEditorField label="名称">
        <input
          value={item.title}
          onChange={(event) => onChangeItem((current) => current.type === 'separator' ? { ...current, title: event.target.value } : current)}
          className="h-7 w-full rounded border border-[var(--color-border)] bg-white px-2 text-xs text-[var(--color-text)] outline-none focus:border-[var(--color-accent)]"
        />
      </CompactEditorField>
    </PanelCard>
  );
}

function CompactEditorField({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-[10px] font-semibold text-[var(--color-text-muted)]">{label}</span>
      {children}
    </label>
  );
}

function TextItemEditor({
  item,
  fallbackFontFamily,
  fallbackFontSize,
  onChange,
}: {
  item: ComposeTextItem;
  fallbackFontFamily: HandoutStyleConfig['fontFamily'];
  fallbackFontSize: number;
  onChange: (patch: Partial<ComposeTextItem>) => void;
}) {
  return (
    <div className="space-y-3">
      <PanelCard title="文本块">
        <div className="space-y-3">
          <div>
            <label className="mb-1 block text-[11px] font-medium text-[var(--color-text-muted)]">名称</label>
            <input
              value={item.title}
              onChange={(event) => onChange({ title: event.target.value })}
              className="h-8 w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-card)] px-2.5 text-sm text-[var(--color-text)] outline-none transition-colors focus:border-[var(--color-accent)]"
            />
          </div>
          <div>
            <label className="mb-1 block text-[11px] font-medium text-[var(--color-text-muted)]">内容</label>
            <StructuredTextEditor
              value={item.content}
              onChange={(value) => onChange({ content: value })}
              document={item.document}
              onDocumentChange={(document) => onChange({ document })}
              placeholder="输入讲义正文、课堂提示或小结"
              minHeight={128}
            />
          </div>
        </div>
      </PanelCard>

      <PanelCard title="文字格式">
        <div className="space-y-2.5">
          <div className="grid grid-cols-2 gap-2">
            <Select
              options={FONT_FAMILY_OPTIONS}
              value={item.style?.fontFamily || fallbackFontFamily}
              onChange={(event) => onChange({ style: { fontFamily: event.target.value as HandoutStyleConfig['fontFamily'] } })}
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
              value={String(item.style?.fontSize || fallbackFontSize)}
              onChange={(event) => onChange({ style: { fontSize: Number(event.target.value) } })}
              size="sm"
            />
          </div>
          <div className="grid grid-cols-4 gap-1">
            {(
              [
                ['left', '左'],
                ['center', '中'],
                ['right', '右'],
              ] as const
            ).map(([value, label]) => (
              <button
                key={value}
                type="button"
                onClick={() => onChange({ style: { textAlign: value } })}
                className={`h-8 rounded-md text-xs font-semibold transition-colors ${
                  (item.style?.textAlign || 'left') === value
                    ? 'bg-[var(--color-accent)] text-white'
                    : 'bg-[var(--color-bg-hover)] text-[var(--color-text-muted)] hover:text-[var(--color-text)]'
                }`}
              >
                {label}
              </button>
            ))}
            <button
              type="button"
              onClick={() => onChange({ style: { fontWeight: item.style?.fontWeight === 'bold' ? 'normal' : 'bold' } })}
              className={`h-8 rounded-md text-xs font-semibold transition-colors ${
                item.style?.fontWeight === 'bold'
                  ? 'bg-[var(--color-accent)] text-white'
                  : 'bg-[var(--color-bg-hover)] text-[var(--color-text-muted)] hover:text-[var(--color-text)]'
              }`}
            >
              加粗
            </button>
          </div>
        </div>
      </PanelCard>
    </div>
  );
}

function PreflightSection({
  report,
  questionCount,
  pageBreakCount,
  saveState,
  paginationReport,
  onLocateQuestion,
  onFixWarning,
}: {
  report: ComposeDiagnosticReport;
  questionCount: number;
  pageBreakCount: number;
  saveState: 'idle' | 'saving' | 'saved' | 'error';
  paginationReport: HandoutPaginationReport | null;
  onLocateQuestion: (questionId: string) => void;
  onFixWarning: (warning: ComposeDiagnosticWarning) => void;
}) {
  const riskCount = report.warnings.filter((warning) => warning.level === 'danger').length;
  const warningCount = report.warnings.filter((warning) => warning.level === 'warning').length;
  const topTypes = Object.entries(report.typeDistribution).slice(0, 3);
  const saveLabel = {
    idle: '等待编辑',
    saving: '正在同步',
    saved: '已同步到草稿库',
    error: '本地已保存，草稿库同步失败',
  }[saveState];

  return (
    <div className="space-y-3">
      <PanelCard title="出稿预检">
        <div className="mb-3 flex items-center justify-between">
          <span
            className={`rounded-md px-2 py-1 text-xs font-semibold ${
              riskCount > 0
                ? 'bg-[var(--color-danger-soft)] text-[var(--color-danger)]'
                : 'bg-[var(--color-success-soft)] text-[var(--color-success)]'
            }`}
          >
            {riskCount > 0 ? `${riskCount} 项风险` : '可出稿'}
          </span>
          <span className="text-[10px] text-[var(--color-text-subtle)]">{saveLabel}</span>
        </div>
        <div className="grid grid-cols-3 gap-2 text-center text-[11px]">
          <MiniStat label="题目" value={questionCount} />
          <MiniStat label="校准页" value={paginationReport?.estimatedPageCount || pageBreakCount + 1} />
          <MiniStat label="警告" value={warningCount} />
        </div>
        {topTypes.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-1.5">
            {topTypes.map(([type, count]) => (
              <span
                key={type}
                className="rounded bg-[var(--color-bg-hover)] px-2 py-1 text-[10px] text-[var(--color-text-muted)]"
              >
                {formatQuestionType(type)} {count}
              </span>
            ))}
          </div>
        )}
      </PanelCard>

      <PanelCard title="结构完整性">
        <CheckRow label="接近满页" value={paginationReport?.nearCapacityPageCount || 0} />
        <CheckRow label="留白过多" value={paginationReport?.sparsePageCount || 0} />
        <CheckRow label="过长内容" value={paginationReport?.oversizedItemCount || 0} danger />
        <CheckRow label="答案缺失" value={report.missingAnswerCount} danger />
        <CheckRow label="解析缺失" value={report.missingAnalysisCount} />
        <CheckRow label="公式异常" value={report.formulaIssueCount} danger />
        <CheckRow label="图片异常" value={report.figureIssueCount} danger />
        <CheckRow label="校对问题" value={report.proofreadingIssueCount} />
      </PanelCard>

      <PanelCard title="问题清单">
        {report.warnings.length === 0 ? (
          <div className="rounded-lg bg-[var(--color-success-soft)] px-2.5 py-2 text-xs leading-5 text-[var(--color-success)]">
            当前没有发现公式、图片、答案或解析的明显异常。
          </div>
        ) : (
          <div className="space-y-2">
            {report.warnings.map((warning, index) => (
              <div
                key={`${warning.message}-${index}`}
                className={`rounded-lg px-2.5 py-2 text-xs leading-5 ${
                  warning.level === 'danger'
                    ? 'bg-[var(--color-danger-soft)] text-[var(--color-danger)]'
                    : warning.level === 'warning'
                      ? 'bg-[var(--color-orange-light)] text-[var(--color-orange)]'
                      : 'bg-[var(--color-bg-hover)] text-[var(--color-text-muted)]'
                } flex w-full items-center gap-2 text-left`}
              >
                <button type="button" disabled={!warning.questionId} onClick={() => warning.questionId && onLocateQuestion(warning.questionId)} className={`min-w-0 flex-1 text-left ${warning.questionId ? 'cursor-pointer' : 'cursor-default'}`}>{warning.message}</button>
                {warning.questionId && warning.code && <button type="button" onClick={() => onFixWarning(warning)} className="shrink-0 rounded border border-current px-2 py-0.5 text-[10px] font-semibold hover:bg-white/70">{warning.code === 'figure' ? '规范尺寸' : '打开修复'}</button>}
              </div>
            ))}
          </div>
        )}
      </PanelCard>
    </div>
  );
}

function CheckRow({ label, value, danger }: { label: string; value: number; danger?: boolean }) {
  const hasIssue = value > 0;
  return (
    <div className="flex items-center justify-between border-t border-[var(--color-border)] py-2 text-xs first:border-t-0">
      <span className="text-[var(--color-text-secondary)]">{label}</span>
      <span
        className={`rounded px-2 py-0.5 font-semibold ${
          hasIssue
            ? danger
              ? 'bg-[var(--color-danger-soft)] text-[var(--color-danger)]'
              : 'bg-[var(--color-orange-light)] text-[var(--color-orange)]'
            : 'bg-[var(--color-success-soft)] text-[var(--color-success)]'
        }`}
      >
        {hasIssue ? value : '通过'}
      </span>
    </div>
  );
}

function MiniStat({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="rounded-lg bg-[var(--color-bg-hover)] px-2 py-2">
      <div className="text-sm font-semibold tabular-nums text-[var(--color-text-main)]">{value}</div>
      <div className="text-[10px] text-[var(--color-text-muted)]">{label}</div>
    </div>
  );
}

/* ═══════════════ Status bar ═══════════════ */

function StatusBar({
  selectedItem,
  questionCount,
  knowledgeCount,
  textCount,
  pageBreakCount,
  totalScore,
  riskCount,
  warningCount,
  saveState,
  zoom,
  layoutLabel,
}: {
  selectedItem: ComposeItem | null;
  questionCount: number;
  knowledgeCount: number;
  textCount: number;
  pageBreakCount: number;
  totalScore: number;
  riskCount: number;
  warningCount: number;
  saveState: 'idle' | 'saving' | 'saved' | 'error';
  zoom: number;
  layoutLabel: string;
}) {
  void knowledgeCount;
  const selectedLabel = selectedItem
    ? selectedItem.type === 'question'
      ? `题目 ${selectedItem.question?.question_id || selectedItem.questionId}`
      : 'title' in selectedItem
        ? selectedItem.title
        : '内容对象'
    : '未选择';

  const saveLabel =
    saveState === 'saving'
      ? '保存中…'
      : saveState === 'saved'
        ? '已保存'
        : saveState === 'error'
          ? '保存失败'
          : '自动保存';

  return (
    <footer className="flex h-[26px] shrink-0 items-center gap-3 border-t border-[#d4deea] bg-[#f8fafc] px-3.5 text-[11px] text-[var(--color-text-muted)] shadow-[0_-1px_0_rgba(255,255,255,0.70)]">
      <div className="min-w-0 flex-1 truncate">
        当前对象：<span className="font-medium text-[var(--color-text-secondary)]">{selectedLabel}</span>
      </div>
      <span className="shrink-0 tabular-nums">
        {questionCount} 题 · {textCount} 文 · {pageBreakCount} 分页 · {totalScore} 分
      </span>
      <span className="shrink-0">{layoutLabel}</span>
      <span className="shrink-0 tabular-nums">{zoom}%</span>
      <span
        className={`shrink-0 font-medium ${
          saveState === 'error'
            ? 'text-[var(--color-danger)]'
            : saveState === 'saved'
              ? 'text-[var(--color-success)]'
              : ''
        }`}
      >
        {saveLabel}
      </span>
      <span
        className={`shrink-0 font-medium ${
          riskCount > 0
            ? 'text-[var(--color-danger)]'
            : warningCount > 0
              ? 'text-[var(--color-orange)]'
              : 'text-[var(--color-success)]'
        }`}
      >
        {riskCount > 0 ? `${riskCount} 风险` : warningCount > 0 ? `${warningCount} 提醒` : '预检通过'}
      </span>
    </footer>
  );
}
