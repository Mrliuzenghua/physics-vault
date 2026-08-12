import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { lazy, Suspense } from 'react';
import { CheckCircle2, ChevronLeft, ChevronRight, Cloud, ExternalLink, FileSearch, History, ImagePlus, PanelRightClose, PanelRightOpen, PencilLine, RotateCcw, Send, Sparkles, Trash2, TriangleAlert, X, ZoomIn, ZoomOut } from 'lucide-react';

import type { FigureInsertRequest } from '../components/editor/StructuredTextEditor';
import LatexRenderer from '../components/render/LatexRenderer';
import ReviewQueueSidebar from '../components/review/ReviewQueueSidebar';
import ImageOptionProcessorDialog from '../components/shared/ImageOptionProcessorDialog';
import type { ImageProcessResult } from '../components/shared/ImageOptionProcessorDialog';
import { useReviewQueue } from '../hooks/review/useReviewQueue';
import {
  analyzeQuestionQuality,
  buildSafeQuestionPatch,
  QUESTION_QUALITY_RULE_LABELS,
  scoreQuestionQuality,
  type QuestionQualityCode,
  type QuestionQualityRuleConfig,
  type QuestionQualitySeverity,
} from '../services/questionQuality';
import { fetchImportTask } from '../services/importApi';
import { requestResponse } from '../services/apiClient';
import {
  deleteReviewDraft,
  fetchReviewDraft,
  fetchReviewDraftVersions,
  restoreReviewDraftVersion,
  ReviewDraftConflictError,
  saveReviewDraft,
} from '../services/reviewDraftApi';
import {
  batchGenerateAnalysis,
  completeImportDraftMetadata,
  deleteReviewTask,
  fetchBatchImages,
  fetchReviewTasks,
  fastCleanReviewLatex,
  generateSingleAnalysis,
  saveReviewedKnowledge,
  saveReviewedQuestions,
  uploadBatchImage,
} from '../services/reviewApi';
import {
  clearReviewCache,
  mediaAssetsFromDrafts,
  mergeMediaAssets,
  mergeTaskMeta,
  readQualityConfig,
  readReviewCache,
  writeQualityConfig,
  writeReviewCache,
  type ReviewPageResult,
  type ReviewTaskMeta,
} from '../services/review/reviewCache';
import type {
  Figure,
  ImportMediaAsset,
  ImportPipelineTaskResponse,
  KnowledgeReviewDraft,
  Question,
  ReviewQuestionDraft,
  ReviewDraftResponse,
  ReviewDraftStatePayload,
  ReviewTaskListItem,
  SaveReviewedKnowledgeResponse,
  SaveReviewedQuestionsResponse,
} from '../types';
import { normalizeShortInlineDisplayMath } from '../utils/mathText';
import { imageThumbnailUrl } from '../utils/imageUrl';
import { findNextMatchingIndex } from '../utils/reviewQueueNavigation';
import { findNextRiskIndex, getRiskItems, type QueueKey } from '../utils/review/reviewQueue';
import {
  applyAiPatch,
  cloneDraft,
  computeFigureIssues,
  displayReviewValue,
  getChangedReviewFields,
  normalizeDraft,
  normalizeKnowledgeDraft,
  normalizeOptions,
} from '../utils/review/reviewDraft';

const QuestionLiveEditor = lazy(() => import('../components/editor/QuestionLiveEditor'));

type ReviewWorkspaceView = 'edit' | 'source';

interface ImageProcessApplyRequest {
  requestId: number;
  questionId: string;
  mode: ImageProcessResult['mode'];
  sourcePath: string;
  uploaded: ImportMediaAsset[];
  createdFigures: Figure[];
}

const TYPE_OPTIONS = [
  { value: 'single_choice', label: '单选题' },
  { value: 'multi_choice', label: '多选题' },
  { value: 'fill', label: '填空题' },
  { value: 'experiment', label: '实验题' },
  { value: 'calculation', label: '计算题' },
];

const TYPE_LABELS = Object.fromEntries(TYPE_OPTIONS.map((item) => [item.value, item.label]));
const INPUT_CLASS = 'w-full rounded-md border border-[var(--color-border)] bg-[var(--color-bg-card)] px-2.5 py-1.5 text-xs text-[var(--color-text)] outline-none focus:border-[var(--color-accent)]';
const TEXTAREA_CLASS = 'w-full resize-y rounded-md border border-[var(--color-border)] bg-[var(--color-bg-card)] px-2.5 py-1.5 text-[13px] leading-6 text-[var(--color-text)] outline-none focus:border-[var(--color-accent)]';
const SOFT_BUTTON_CLASS = 'rounded-md border border-[var(--color-border)] bg-[var(--color-bg-card)] px-2.5 py-1.5 text-xs font-semibold text-[var(--color-text-secondary)] disabled:cursor-not-allowed disabled:opacity-45';
const PRIMARY_BUTTON_CLASS = 'rounded-md bg-[var(--color-accent)] px-2.5 py-1.5 text-xs font-semibold text-white disabled:cursor-not-allowed disabled:opacity-45';
const TABLE_TEMPLATE = '\n\n| 项目 | 内容 |\n| --- | --- |\n|  |  |';
const REVIEW_FIELD_LABELS: Partial<Record<keyof ReviewQuestionDraft, string>> = {
  question_type: '题型',
  title: '题干',
  options: '选项',
  answer: '答案',
  analysis: '解析',
  difficulty: '难度',
  knowledge_point: '知识点',
  tags: '标签',
  source: '来源',
  figures: '配图',
};

function appendTableTemplate(value: string): string {
  return `${value.trimEnd()}${TABLE_TEMPLATE}`.trimStart();
}

function fileUrl(path?: string | null): string | null {
  const trimmed = String(path || '').trim();
  if (!trimmed) return null;
  if (trimmed.startsWith('/files/')) return trimmed;
  return `/files/${trimmed.replace(/^\.?\//, '')}`;
}

function applyImageProcessToDraft(draft: ReviewQuestionDraft, request: ImageProcessApplyRequest): ReviewQuestionDraft {
  const sourceFigure = draft.figures.find((figure) => figure.local_path === request.sourcePath);
  const sourceMarker = sourceFigure ? `![fig:${sourceFigure.fig_uuid}]` : '';
  const cleanMarker = (value: string) => sourceMarker
    ? value.split(sourceMarker).join('').replace(/\n{3,}/g, '\n\n').trim()
    : value;

  if (request.mode === 'split') {
    const currentOptions = new Map(draft.options.map((option) => [option.opt.toUpperCase(), option]));
    const options = ['A', 'B', 'C', 'D'].map((letter, index) => {
      const current = currentOptions.get(letter) || { opt: letter, content: '' };
      const content = cleanMarker(current.content);
      return {
        ...current,
        opt: letter,
        content: `${content}${content ? '\n' : ''}![fig:${request.createdFigures[index].fig_uuid}]`,
      };
    });
    return {
      ...draft,
      title: cleanMarker(draft.title),
      options,
      figures: [...draft.figures.filter((figure) => figure !== sourceFigure), ...request.createdFigures],
    };
  }

  const replacement = request.createdFigures[0];
  if (!replacement) return draft;
  if (sourceFigure) {
    return {
      ...draft,
      figures: draft.figures.map((figure) => figure === sourceFigure ? { ...figure, local_path: replacement.local_path } : figure),
    };
  }
  return {
    ...draft,
    title: `${draft.title.trim()}\n\n![fig:${replacement.fig_uuid}]`.trim(),
    figures: [...draft.figures, replacement],
  };
}

function getKnowledgeRisks(draft: KnowledgeReviewDraft): string[] {
  return [
    !draft.topic3_name.trim() ? '缺少知识点名称' : '',
    !draft.topic3_id.trim() ? '缺少知识点 ID' : '',
    !draft.definition.trim() ? '缺少标准定义或核心表述' : '',
    !draft.topic2_name.trim() && !draft.topic2_id.trim() ? '缺少所属二级章节' : '',
  ].filter(Boolean);
}

export default function ReviewWorkbenchPage() {
  const { taskId } = useParams<{ taskId: string }>();
  const navigate = useNavigate();
  const originalsRef = useRef<Map<string, ReviewQuestionDraft>>(new Map());
  const serverVersionRef = useRef(0);
  const serverSavingRef = useRef(false);
  const pendingServerSaveRef = useRef<ReviewDraftStatePayload | null>(null);
  const pendingServerSaveSignatureRef = useRef('');
  const savingServerStateSignatureRef = useRef('');
  const savedServerStateSignatureRef = useRef('');
  const serverAutosaveReadyRef = useRef(false);
  const serverConflictRef = useRef(false);
  const remoteSignatureRef = useRef('');
  const lastLocalChangeAtRef = useRef(0);
  const currentQuestionIdRef = useRef<string | null>(null);

  const [drafts, setDrafts] = useState<ReviewQuestionDraft[]>([]);
  const [knowledgeDrafts, setKnowledgeDrafts] = useState<KnowledgeReviewDraft[]>([]);
  const [taskMeta, setTaskMeta] = useState<ReviewTaskMeta>({ warnings: [], pageResults: [], mediaAssets: [] });
  const [workspaceView, setWorkspaceView] = useState<ReviewWorkspaceView>('edit');
  const [toolsOpen, setToolsOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [aiProcessing, setAiProcessing] = useState(false);
  const [aiMessage, setAiMessage] = useState<string | null>(null);
  const [aiSuggestion, setAiSuggestion] = useState<Partial<ReviewQuestionDraft> | null>(null);
  const [copyMessage, setCopyMessage] = useState<string | null>(null);
  const [cacheMessage, setCacheMessage] = useState<string | null>(null);
  const [, setCacheSavedAt] = useState<Date | null>(null);
  const [serverDraftVersion, setServerDraftVersion] = useState(0);
  const [serverDraftUpdatedAt, setServerDraftUpdatedAt] = useState<Date | null>(null);
  const [serverDraftStatus, setServerDraftStatus] = useState<'idle' | 'saving' | 'saved' | 'offline' | 'conflict'>('idle');
  const [serverConflict, setServerConflict] = useState<ReviewDraftResponse | null>(null);
  const [draftVersions, setDraftVersions] = useState<ReviewDraftResponse[]>([]);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saveResult, setSaveResult] = useState<SaveReviewedQuestionsResponse | null>(null);
  const [knowledgeSaveResult, setKnowledgeSaveResult] = useState<SaveReviewedKnowledgeResponse | null>(null);
  const [reviewTasks, setReviewTasks] = useState<ReviewTaskListItem[]>([]);
  const [reviewTasksLoading, setReviewTasksLoading] = useState(false);
  const [reviewTasksError, setReviewTasksError] = useState<string | null>(null);
  const [deletingTaskId, setDeletingTaskId] = useState<string | null>(null);
  const [imageUploading, setImageUploading] = useState(false);
  const [imagePickerOpen, setImagePickerOpen] = useState(false);
  const [figureInsertQueue, setFigureInsertQueue] = useState<FigureInsertRequest[]>([]);
  const figureInsertRequest = figureInsertQueue[0] ?? null;
  const [imageProcessRequest, setImageProcessRequest] = useState<ImageProcessApplyRequest | null>(null);
  const [qualityConfig, setQualityConfig] = useState<QuestionQualityRuleConfig>(() => readQualityConfig());
  const {
    counts,
    currentDraft,
    currentIndex,
    currentPage,
    duplicateQuestionIds,
    filteredDrafts,
    goNext,
    goNextRisk,
    goPrevious,
    qualityReport,
    questionQuery,
    queue,
    setCurrentIndex,
    setQuestionQuery,
    setQueue,
  } = useReviewQueue({ drafts, pageResults: taskMeta.pageResults, qualityConfig });

  const loadReviewTasks = useCallback(async () => {
    setReviewTasksLoading(true);
    setReviewTasksError(null);
    try {
      const result = await fetchReviewTasks();
      setReviewTasks(result.items || []);
    } catch (err) {
      setReviewTasksError(err instanceof Error ? err.message : '加载审核任务失败');
    } finally {
      setReviewTasksLoading(false);
    }
  }, []);

  useEffect(() => {
    if (taskId) return;
    void loadReviewTasks();
  }, [loadReviewTasks, taskId]);

  const handleDeleteReviewTask = useCallback(async (id: string) => {
    const confirmed = window.confirm('删除这个审核任务？只会移出校对中心队列，不会删除正式题库或知识点库。');
    if (!confirmed) return;
    setDeletingTaskId(id);
    setReviewTasksError(null);
    try {
      await deleteReviewTask(id);
      setReviewTasks((prev) => prev.filter((task) => task.task_id !== id));
      clearReviewCache(id);
    } catch (err) {
      setReviewTasksError(err instanceof Error ? err.message : '删除审核任务失败');
    } finally {
      setDeletingTaskId(null);
    }
  }, []);

  useEffect(() => {
    if (!taskId) return;
    setLoading(true);
    setError(null);
    serverAutosaveReadyRef.current = false;
    serverConflictRef.current = false;
    pendingServerSaveRef.current = null;
    pendingServerSaveSignatureRef.current = '';
    savingServerStateSignatureRef.current = '';
    savedServerStateSignatureRef.current = '';
    Promise.all([
      fetchImportTask(taskId),
      fetchReviewDraft(taskId).catch(() => ({ draft: null, unavailable: true })),
    ])
      .then(async ([task, draftLookup]: [ImportPipelineTaskResponse, { draft: ReviewDraftResponse | null; unavailable?: boolean }]) => {
        const result = task.result ?? {};
        const questions = Array.isArray(result.questions) ? result.questions as Record<string, unknown>[] : [];
        const parsed = questions.map((raw, index) => normalizeDraft(raw, index));
        remoteSignatureRef.current = JSON.stringify(questions);
        const knowledgeItems = Array.isArray(result.knowledge_drafts) ? result.knowledge_drafts as Record<string, unknown>[] : [];
        const parsedKnowledge = knowledgeItems.map((raw, index) => normalizeKnowledgeDraft(raw, index));
        const batchId = String(result.batch_id || task.input_summary?.batch_id || '');
        const resultMediaAssets = Array.isArray(result.media_assets) ? result.media_assets as ImportMediaAsset[] : [];
        const batchMediaAssets = batchId ? await fetchBatchImages(batchId).catch(() => []) : [];
        const meta = {
          batchId,
          warnings: Array.isArray(result.warnings) ? result.warnings.map(String) : [],
          pageResults: Array.isArray(result.page_results) ? result.page_results as ReviewPageResult[] : [],
          mediaAssets: mergeMediaAssets(resultMediaAssets, batchMediaAssets, mediaAssetsFromDrafts(parsed)),
        };
        const cached = readReviewCache<QueueKey>(taskId);
        const serverDraft = draftLookup.draft;
        const cachedIsNewer = Boolean(cached && (!serverDraft || Date.parse(cached.savedAt) > Date.parse(serverDraft.updated_at)));
        originalsRef.current = new Map(parsed.map((draft) => [draft.question_id, cloneDraft(draft)]));
        serverVersionRef.current = serverDraft?.version ?? 0;
        savedServerStateSignatureRef.current = serverDraft ? JSON.stringify(serverDraft.state) : '';
        setServerDraftVersion(serverDraft?.version ?? 0);
        setServerDraftUpdatedAt(serverDraft ? new Date(serverDraft.updated_at) : null);
        setServerDraftStatus(draftLookup.unavailable ? 'offline' : serverDraft ? 'saved' : 'idle');
        if (cached?.drafts.length && cachedIsNewer) {
          const restored = cached.drafts.map((draft, index) => normalizeDraft(draft as unknown as Record<string, unknown>, index));
          setDrafts(restored);
          setKnowledgeDrafts(cached.knowledgeDrafts ?? parsedKnowledge);
          setTaskMeta(mergeTaskMeta(cached.taskMeta, meta, restored));
          setCurrentIndex(Math.min(cached.currentIndex ?? 0, Math.max(restored.length - 1, 0)));
          setQueue(cached.queue ?? 'risk');
          setCacheMessage(`已恢复 ${new Date(cached.savedAt).toLocaleString()} 的较新本地草稿`);
        } else if (serverDraft?.state.drafts.length) {
          const restored = serverDraft.state.drafts.map((draft, index) => normalizeDraft(draft as unknown as Record<string, unknown>, index));
          setDrafts(restored);
          setKnowledgeDrafts((serverDraft.state.knowledge_drafts ?? []).map((draft, index) => normalizeKnowledgeDraft(draft as unknown as Record<string, unknown>, index)));
          setTaskMeta(mergeTaskMeta(serverDraft.state.task_meta as unknown as ReviewTaskMeta, meta, restored));
          setCurrentIndex(Math.min(serverDraft.state.current_index ?? 0, Math.max(restored.length - 1, 0)));
          setQueue((serverDraft.state.queue as QueueKey) ?? 'risk');
          setCacheMessage(`已恢复服务器草稿 v${serverDraft.version}`);
        } else {
          setDrafts(parsed);
          setKnowledgeDrafts(parsedKnowledge);
          setTaskMeta(mergeTaskMeta(null, meta, parsed));
          setCurrentIndex(0);
          setCacheMessage(null);
        }
      })
      .catch((err: unknown) => setError(err instanceof Error ? err.message : '加载校对任务失败'))
      .finally(() => {
        setLoading(false);
        window.setTimeout(() => { serverAutosaveReadyRef.current = true; }, 0);
      });
  }, [setCurrentIndex, setQueue, taskId]);

  useEffect(() => {
    currentQuestionIdRef.current = drafts[currentIndex]?.question_id ?? null;
  }, [currentIndex, drafts]);

  // MCP/AI may update result_json outside this browser tab. Pull it back into
  // the editor so the risk queue is recalculated without a manual reload.
  useEffect(() => {
    if (!taskId || loading) return;
    let active = true;
    const syncRemoteTask = async () => {
      if (!active || serverSavingRef.current || pendingServerSaveRef.current || serverConflictRef.current) return;
      if (Date.now() - lastLocalChangeAtRef.current < 5000) return;
      try {
        const task = await fetchImportTask(taskId);
        const result = task.result ?? {};
        const questions = Array.isArray(result.questions) ? result.questions as Record<string, unknown>[] : [];
        const signature = JSON.stringify(questions);
        if (!signature || signature === remoteSignatureRef.current) return;
        const parsed = questions.map((raw, index) => normalizeDraft(raw, index));
        remoteSignatureRef.current = signature;
        originalsRef.current = new Map(parsed.map((draft) => [draft.question_id, cloneDraft(draft)]));
        setDrafts(parsed);
        setTaskMeta((previous) => ({
          ...previous,
          warnings: Array.isArray(result.warnings) ? result.warnings.map(String) : previous.warnings,
          pageResults: Array.isArray(result.page_results) ? result.page_results as ReviewPageResult[] : previous.pageResults,
          mediaAssets: mergeMediaAssets(previous.mediaAssets, mediaAssetsFromDrafts(parsed)),
        }));
        const nextIndex = Math.max(0, parsed.findIndex((draft) => draft.question_id === currentQuestionIdRef.current));
        setCurrentIndex(nextIndex);
        setCacheMessage('AI 修改已同步，风险已重新校验');
      } catch {
        // The normal editor remains usable while the background check retries.
      }
    };
    void syncRemoteTask();
    const timer = window.setInterval(() => void syncRemoteTask(), 4000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [loading, setCurrentIndex, taskId]);

  const currentOriginal = currentDraft ? originalsRef.current.get(currentDraft.question_id) ?? null : null;

  useEffect(() => writeQualityConfig(qualityConfig), [qualityConfig]);

  useEffect(() => {
    if (!taskId || loading || drafts.length === 0) return;
    setCacheMessage('正在保存本地草稿...');
    const timer = window.setTimeout(() => {
      writeReviewCache(taskId, { drafts, qualityReport, knowledgeDrafts, taskMeta, currentIndex, queue });
      const savedAt = new Date();
      setCacheSavedAt(savedAt);
      setCacheMessage(`已自动保存 ${savedAt.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`);
    }, 500);
    return () => window.clearTimeout(timer);
  }, [currentIndex, drafts, knowledgeDrafts, loading, qualityReport, queue, taskId, taskMeta]);

  const flushServerDraft = useCallback(async () => {
    if (!taskId || serverSavingRef.current || serverConflictRef.current) return;
    const state = pendingServerSaveRef.current;
    if (!state) return;
    const stateSignature = pendingServerSaveSignatureRef.current || JSON.stringify(state);
    pendingServerSaveRef.current = null;
    pendingServerSaveSignatureRef.current = '';
    serverSavingRef.current = true;
    savingServerStateSignatureRef.current = stateSignature;
    setServerDraftStatus('saving');
    try {
      const saved = await saveReviewDraft(taskId, { base_version: serverVersionRef.current, state });
      serverVersionRef.current = saved.version;
      savedServerStateSignatureRef.current = stateSignature;
      setServerDraftVersion(saved.version);
      setServerDraftUpdatedAt(new Date(saved.updated_at));
      setServerDraftStatus('saved');
    } catch (err) {
      if (err instanceof ReviewDraftConflictError) {
        serverConflictRef.current = true;
        setServerConflict(err.current);
        setServerDraftStatus('conflict');
      } else {
        pendingServerSaveRef.current = state;
        pendingServerSaveSignatureRef.current = stateSignature;
        setServerDraftStatus('offline');
      }
    } finally {
      serverSavingRef.current = false;
      savingServerStateSignatureRef.current = '';
      if (pendingServerSaveRef.current && !serverConflictRef.current) {
        window.setTimeout(() => void flushServerDraft(), 0);
      }
    }
  }, [taskId]);

  useEffect(() => {
    if (!taskId || loading || drafts.length === 0 || !serverAutosaveReadyRef.current || serverConflictRef.current) return;
    // Serializing an entire review task is expensive for large imports. Keep
    // it out of the keystroke path and only prepare a save after the user has
    // paused typing.
    const timer = window.setTimeout(() => {
      const state = {
        drafts,
        knowledge_drafts: knowledgeDrafts,
        task_meta: taskMeta as unknown as Record<string, unknown>,
        current_index: currentIndex,
        queue,
      };
      const stateSignature = JSON.stringify(state);
      // Several editor callbacks can report the same document. Do not keep
      // creating new draft versions for an unchanged state.
      if (
        stateSignature === savedServerStateSignatureRef.current
        || stateSignature === pendingServerSaveSignatureRef.current
        || stateSignature === savingServerStateSignatureRef.current
      ) return;
      pendingServerSaveRef.current = state;
      pendingServerSaveSignatureRef.current = stateSignature;
      void flushServerDraft();
    }, 1400);
    return () => window.clearTimeout(timer);
  }, [currentIndex, drafts, flushServerDraft, knowledgeDrafts, loading, queue, taskId, taskMeta]);

  const applyServerSnapshot = useCallback((snapshot: ReviewDraftResponse, message: string) => {
    const restored = snapshot.state.drafts.map((draft, index) => normalizeDraft(draft as unknown as Record<string, unknown>, index));
    serverAutosaveReadyRef.current = false;
    serverConflictRef.current = false;
    pendingServerSaveRef.current = null;
    pendingServerSaveSignatureRef.current = '';
    savingServerStateSignatureRef.current = '';
    serverVersionRef.current = snapshot.version;
    savedServerStateSignatureRef.current = JSON.stringify(snapshot.state);
    setDrafts(restored);
    setKnowledgeDrafts((snapshot.state.knowledge_drafts ?? []).map((draft, index) => normalizeKnowledgeDraft(draft as unknown as Record<string, unknown>, index)));
    setTaskMeta((current) => mergeTaskMeta(snapshot.state.task_meta as unknown as ReviewTaskMeta, current, restored));
    setCurrentIndex(Math.min(snapshot.state.current_index ?? 0, Math.max(restored.length - 1, 0)));
    setQueue((snapshot.state.queue as QueueKey) ?? 'risk');
    setServerDraftVersion(snapshot.version);
    setServerDraftUpdatedAt(new Date(snapshot.updated_at));
    setServerDraftStatus('saved');
    setServerConflict(null);
    setCacheMessage(message);
    window.setTimeout(() => { serverAutosaveReadyRef.current = true; }, 0);
  }, [setCurrentIndex, setQueue]);

  const handleLoadServerConflict = useCallback(() => {
    if (!serverConflict) return;
    applyServerSnapshot(serverConflict, `已加载服务器草稿 v${serverConflict.version}，本页未保存修改仍保留在本地缓存中`);
  }, [applyServerSnapshot, serverConflict]);

  const handleToggleHistory = useCallback(async () => {
    if (!taskId) return;
    const willOpen = !historyOpen;
    setHistoryOpen(willOpen);
    if (!willOpen) return;
    setHistoryLoading(true);
    try {
      const result = await fetchReviewDraftVersions(taskId, 12);
      setDraftVersions(result.items);
    } catch (err) {
      setCacheMessage(`读取历史版本失败：${err instanceof Error ? err.message : '未知错误'}`);
    } finally {
      setHistoryLoading(false);
    }
  }, [historyOpen, taskId]);

  const handleRestoreVersion = useCallback(async (version: number) => {
    if (!taskId || version === serverVersionRef.current) return;
    const confirmed = window.confirm(`恢复到服务器草稿 v${version}？当前版本仍会保留在历史记录中。`);
    if (!confirmed) return;
    setHistoryLoading(true);
    try {
      const restored = await restoreReviewDraftVersion(taskId, version, serverVersionRef.current);
      applyServerSnapshot(restored, `已恢复历史草稿 v${version}，并生成新版本 v${restored.version}`);
      const result = await fetchReviewDraftVersions(taskId, 12);
      setDraftVersions(result.items);
    } catch (err) {
      setCacheMessage(`恢复历史版本失败：${err instanceof Error ? err.message : '未知错误'}`);
    } finally {
      setHistoryLoading(false);
    }
  }, [applyServerSnapshot, taskId]);

  const updateDraftAt = useCallback((index: number, patch: Partial<ReviewQuestionDraft>) => {
    lastLocalChangeAtRef.current = Date.now();
    setDrafts((prev) => {
      const next = [...prev];
      const updated = { ...next[index], ...patch };
      updated.title = normalizeShortInlineDisplayMath(updated.title);
      updated.answer = normalizeShortInlineDisplayMath(updated.answer);
      updated.analysis = normalizeShortInlineDisplayMath(updated.analysis);
      updated.options = normalizeOptions(updated.options);
      updated.figureIssues = computeFigureIssues(updated);
      if (updated.status === 'pending') updated.status = 'modified';
      next[index] = updated;
      return next;
    });
    setAiSuggestion(null);
  }, []);

  const updateCurrentField = useCallback((field: keyof ReviewQuestionDraft, value: unknown) => {
    if (!currentDraft) return;
    updateDraftAt(currentIndex, { [field]: value } as Partial<ReviewQuestionDraft>);
  }, [currentDraft, currentIndex, updateDraftAt]);

  const updateStatus = useCallback((status: ReviewQuestionDraft['status']) => {
    setDrafts((prev) => prev.map((draft, index) => index === currentIndex ? { ...draft, status } : draft));
  }, [currentIndex]);

  const confirmAndNext = useCallback(() => {
    if (!currentDraft) return;
    const blockingRisks = getRiskItems(currentDraft, duplicateQuestionIds, qualityConfig).filter((risk) => risk.severity === 'danger');
    if (blockingRisks.length > 0) {
      const shouldContinue = window.confirm(`当前题仍有关键问题：\n${blockingRisks.map((risk) => `• ${risk.message}`).join('\n')}\n\n仍要确认这道题吗？`);
      if (!shouldContinue) return;
    }
    updateStatus('confirmed');

    if (queue === 'risk' || queue === 'pending') {
      const nextInActiveQueue = findNextMatchingIndex(
        drafts,
        currentIndex,
        (draft) => queue === 'pending'
          ? draft.status === 'pending'
          : draft.status !== 'discarded' && getRiskItems(draft, duplicateQuestionIds, qualityConfig).length > 0,
      );
      if (nextInActiveQueue !== null) {
        setCurrentIndex(nextInActiveQueue);
      } else {
        setCacheMessage(`当前“${queue === 'risk' ? '风险' : '待确认'}”队列已无其它题目`);
      }
      return;
    }

    const nextRisk = findNextRiskIndex(drafts, currentIndex, duplicateQuestionIds, qualityConfig);
    if (nextRisk !== null) setCurrentIndex(nextRisk);
    else goNext();
  }, [currentDraft, currentIndex, drafts, duplicateQuestionIds, goNext, qualityConfig, queue, setCurrentIndex, updateStatus]);

  const restoreCurrent = useCallback(() => {
    if (!currentDraft) return;
    const original = originalsRef.current.get(currentDraft.question_id);
    if (!original) return;
    setDrafts((prev) => prev.map((draft, index) => index === currentIndex ? cloneDraft(original) : draft));
    setAiSuggestion(null);
  }, [currentDraft, currentIndex]);

  const copyText = useCallback(async (text: string, message: string) => {
    await navigator.clipboard.writeText(text);
    setCopyMessage(message);
    window.setTimeout(() => setCopyMessage(null), 1800);
  }, []);

  const copyImage = useCallback(async (asset: ImportMediaAsset) => {
    const imageUrl = /\.(?:wmf|emf)$/i.test(asset.relative_path)
      ? imageThumbnailUrl(asset.relative_path, 1600)
      : fileUrl(asset.relative_path);
    if (!imageUrl || !navigator.clipboard || typeof ClipboardItem === 'undefined') {
      setCopyMessage('当前浏览器不支持直接复制图片');
      window.setTimeout(() => setCopyMessage(null), 1800);
      return;
    }
    try {
      const response = await requestResponse(imageUrl);
      const blob = await response.blob();
      await navigator.clipboard.write([new ClipboardItem({ [blob.type || 'image/png']: blob })]);
      setCopyMessage('已复制图片');
    } catch {
      setCopyMessage('复制图片失败，请复制路径后手动打开');
    }
    window.setTimeout(() => setCopyMessage(null), 1800);
  }, []);

  const attachAssetToCurrent = useCallback((asset: ImportMediaAsset) => {
    if (!currentDraft) return;
    const uuid = `fig_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 7)}`;
    const figure = { fig_uuid: uuid, local_path: asset.relative_path, display_scale: 60, display_align: 'center' as const };
    setFigureInsertQueue((queue) => [...queue, { requestId: Date.now() + Math.random(), figure }]);
    setCopyMessage(`已插入图片 ${uuid}`);
    window.setTimeout(() => setCopyMessage(null), 1800);
  }, [currentDraft]);

  const handleUploadImageToCurrent = useCallback(async (file: File) => {
    if (!currentDraft) return;
    const batchId = taskMeta.batchId?.trim();
    if (!batchId) {
      setCopyMessage('当前任务没有可用图片缓存目录');
      window.setTimeout(() => setCopyMessage(null), 1800);
      return;
    }
    setImageUploading(true);
    setCopyMessage('正在上传图片...');
    try {
      const asset = await uploadBatchImage(batchId, file);
      setTaskMeta((prev) => ({ ...prev, mediaAssets: [...prev.mediaAssets, asset] }));
      const uuid = `fig_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 7)}`;
      const figure = { fig_uuid: uuid, local_path: asset.relative_path, display_scale: 60, display_align: 'center' as const };
      setFigureInsertQueue((queue) => [...queue, { requestId: Date.now() + Math.random(), figure }]);
      setCopyMessage(`已上传并插入图片 ${uuid}`);
    } catch (err) {
      setCopyMessage(`上传失败：${err instanceof Error ? err.message : '未知错误'}`);
    } finally {
      setImageUploading(false);
      window.setTimeout(() => setCopyMessage(null), 2200);
    }
  }, [currentDraft, taskMeta.batchId]);

  const handleProcessImageForCurrent = useCallback(async (sourceAsset: ImportMediaAsset, result: ImageProcessResult) => {
    if (!currentDraft) throw new Error('请先选择一道题目');
    const batchId = taskMeta.batchId?.trim();
    if (!batchId) throw new Error('当前任务没有可用图片缓存目录');
    const uploaded: ImportMediaAsset[] = [];
    for (const file of result.files) uploaded.push(await uploadBatchImage(batchId, file));
    setTaskMeta((previous) => ({ ...previous, mediaAssets: mergeMediaAssets(previous.mediaAssets, uploaded) }));

    if (uploaded.length !== result.files.length) throw new Error('部分图片未能保存，请重试');
    const createdFigures: Figure[] = result.mode === 'split'
      ? uploaded.map((asset, index) => ({
        fig_uuid: `fig_option_${Date.now().toString(36)}_${index}_${Math.random().toString(36).slice(2, 6)}`,
        local_path: asset.relative_path,
        display_scale: 100,
        display_align: 'center',
      }))
      : [{
          fig_uuid: `fig_enhanced_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 6)}`,
          local_path: uploaded[0].relative_path,
          display_scale: 60,
          display_align: 'center',
        }];
    setImageProcessRequest({
      requestId: Date.now() + Math.random(),
      questionId: currentDraft.question_id,
      mode: result.mode,
      sourcePath: sourceAsset.relative_path,
      uploaded,
      createdFigures,
    });
    setCopyMessage(result.mode === 'split' ? '已切分为 A/B/C/D 四张 PNG 并写入选项' : '清晰化 PNG 已应用到当前题');
    window.setTimeout(() => setCopyMessage(null), 2200);
  }, [currentDraft, taskMeta.batchId]);

  const handleSingleAiSuggestion = useCallback(async () => {
    if (!currentDraft) return;
    setAiProcessing(true);
    setAiMessage(`正在为第 ${currentIndex + 1} 题生成修复建议...`);
    try {
      const { figureIssues: _figureIssues, status: _status, ...question } = currentDraft;
      const result = await generateSingleAnalysis({ question, style: 'classroom_brief' });
      if (!result.generated || !result.analysis_text) {
        setAiMessage(`AI 未生成建议：${result.warnings?.join('，') || '服务未启用'}`);
        return;
      }
      const patch = applyAiPatch(result.analysis_text);
      setAiSuggestion(patch);
      setAiMessage(`已生成建议：${Object.keys(patch).join('、') || '解析'}`);
    } catch (err) {
      setAiMessage(`AI 建议失败：${err instanceof Error ? err.message : '未知错误'}`);
    } finally {
      setAiProcessing(false);
    }
  }, [currentDraft, currentIndex]);

  const acceptSuggestion = useCallback(() => {
    if (!aiSuggestion || !currentDraft) return;
    updateDraftAt(currentIndex, aiSuggestion);
    setAiSuggestion(null);
  }, [aiSuggestion, currentDraft, currentIndex, updateDraftAt]);

  const handleBatchAnalysis = useCallback(async () => {
    const ids = drafts.filter((draft) => draft.status !== 'discarded').map((draft) => draft.question_id);
    if (ids.length === 0) return setAiMessage('没有可处理的题目');
    setAiProcessing(true);
    setAiMessage('正在批量生成解析...');
    try {
      const result = await batchGenerateAnalysis({ question_ids: ids, style: 'classroom_brief', include_extension: false, force_regenerate: false });
      setAiMessage(`解析生成完成：成功 ${result.success_count}，跳过 ${result.skipped_count}，失败 ${result.failed_count}`);
    } catch (err) {
      setAiMessage(`批量解析失败：${err instanceof Error ? err.message : '未知错误'}`);
    } finally {
      setAiProcessing(false);
    }
  }, [drafts]);

  const handleBatchMetadata = useCallback(async () => {
    const candidates = drafts.filter((draft) => draft.status !== 'discarded');
    if (candidates.length === 0) return setAiMessage('没有可处理的题目');
    const batchId = candidates.find((draft) => draft.import_batch_id)?.import_batch_id ?? taskId ?? 'review';
    setAiProcessing(true);
    setAiMessage('正在 AI 补全知识点、标签和来源...');
    try {
      const result = await completeImportDraftMetadata(batchId, {
        questions: candidates.map(({ figureIssues: _figureIssues, status: _status, ...question }) => question),
        fields: ['knowledge_points', 'tags', 'source'],
        force_overwrite: false,
      });
      const byId = new Map(result.questions.map((question) => [String(question.question_id ?? ''), question]));
      setDrafts((prev) => prev.map((draft) => {
        const updated = byId.get(draft.question_id);
        if (!updated) return draft;
        const merged = normalizeDraft({ ...draft, ...updated }, 0);
        return {
          ...draft,
          knowledge_point: merged.knowledge_point,
          tags: merged.tags,
          source: merged.source,
          status: draft.status === 'pending' ? 'modified' : draft.status,
        };
      }));
      const warningText = result.warnings?.length ? `；提示：${result.warnings.join('；')}` : '';
      setAiMessage(`元数据补全完成：更新 ${result.updated}，跳过 ${result.skipped}，失败 ${result.failed}${warningText}`);
    } catch (err) {
      setAiMessage(`元数据补全失败：${err instanceof Error ? err.message : '未知错误'}`);
    } finally {
      setAiProcessing(false);
    }
  }, [drafts, taskId]);

  const handleExportJSON = useCallback(() => {
    const exportData = drafts.map(({ figureIssues: _figureIssues, status, ...draft }) => ({ ...draft, review_status: status }));
    const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `review-draft-${taskId ?? 'unknown'}.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  }, [drafts, taskId]);

  const handleSave = useCallback(async () => {
    const confirmed = drafts.filter((draft) => draft.status === 'confirmed');
    if (confirmed.length === 0) {
      setSaveError('没有已确认题目。请先确认至少一道题，再保存入库。');
      return;
    }
    setSaving(true);
    setSaveError(null);
    try {
      const questions = confirmed.map(({ figureIssues: _figureIssues, status, ...draft }) => ({ ...draft, review_status: status }));
      const result = await saveReviewedQuestions({ task_id: taskId ?? 'review', questions });
      setSaveResult(result);
      if (taskId) {
        await deleteReviewDraft(taskId);
        clearReviewCache(taskId);
        serverVersionRef.current = 0;
        setServerDraftVersion(0);
        setServerDraftStatus('idle');
        setCacheMessage('已保存入库，本地与服务器校对草稿已清除');
      }
    } catch (err) {
      setSaveError(`保存失败：${err instanceof Error ? err.message : '未知错误'}`);
    } finally {
      setSaving(false);
    }
  }, [drafts, taskId]);

  const handleSubmitReview = useCallback(async () => {
    const unfinished = counts.pending + counts.modified;
    if (unfinished > 0) {
      const confirmed = window.confirm(`还有 ${unfinished} 道题尚未确认。本次只提交已确认的 ${counts.confirmed} 道题，是否继续？`);
      if (!confirmed) return;
    }
    await handleSave();
  }, [counts.confirmed, counts.modified, counts.pending, handleSave]);

  const handleFastLatexCleanup = useCallback(async () => {
    if (!taskId) return;
    setAiProcessing(true);
    setAiMessage('正在快速清洗 LaTeX，不调用 Claude Code...');
    try {
      const result = await fastCleanReviewLatex({ task_id: taskId, dry_run: false });
      setAiMessage(
        `快速清洗完成：影响 ${result.changed_questions} 题，替换 ${result.replacement_count} 处，用时 ${result.elapsed_ms}ms。正在刷新任务...`,
      );
      const task = await fetchImportTask(taskId);
      const taskResult = task.result ?? {};
      const questions = Array.isArray(taskResult.questions) ? taskResult.questions as Record<string, unknown>[] : [];
      const parsed = questions.map((raw, index) => normalizeDraft(raw, index));
      originalsRef.current = new Map(parsed.map((draft) => [draft.question_id, cloneDraft(draft)]));
      setDrafts(parsed);
      clearReviewCache(taskId);
      setCacheMessage('已刷新快速清洗后的审核草稿，本地旧缓存已清除');
    } catch (err) {
      setAiMessage(`快速清洗失败：${err instanceof Error ? err.message : '未知错误'}`);
    } finally {
      setAiProcessing(false);
    }
  }, [taskId]);

  const updateKnowledgeDraft = useCallback((index: number, patch: Partial<KnowledgeReviewDraft>) => {
    setKnowledgeDrafts((prev) => {
      const next = [...prev];
      const updated = { ...next[index], ...patch };
      if (updated.status === 'pending') updated.status = 'modified';
      next[index] = updated;
      return next;
    });
  }, []);

  const setKnowledgeStatus = useCallback((index: number, status: KnowledgeReviewDraft['status']) => {
    setKnowledgeDrafts((prev) => prev.map((draft, draftIndex) => draftIndex === index ? { ...draft, status } : draft));
  }, []);

  const handleSaveKnowledge = useCallback(async () => {
    const confirmed = knowledgeDrafts.filter((draft) => draft.status === 'confirmed');
    if (confirmed.length === 0) {
      setSaveError('没有已确认知识点。请先确认至少一个知识点，再保存入库。');
      return;
    }
    setSaving(true);
    setSaveError(null);
    try {
      const result = await saveReviewedKnowledge({
        task_id: taskId ?? 'review',
        knowledge_drafts: confirmed.map((draft) => ({ ...draft, review_status: draft.status })),
      });
      setKnowledgeSaveResult(result);
    } catch (err) {
      setSaveError(`保存知识点失败：${err instanceof Error ? err.message : '未知错误'}`);
    } finally {
      setSaving(false);
    }
  }, [knowledgeDrafts, taskId]);

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      const target = event.target;
      const isEditing = target instanceof HTMLInputElement
        || target instanceof HTMLTextAreaElement
        || target instanceof HTMLSelectElement
        || (target instanceof HTMLElement && target.isContentEditable);
      if ((event.metaKey || event.ctrlKey) && event.key === 'Enter') {
        event.preventDefault();
        confirmAndNext();
        return;
      }
      if (isEditing) return;
      if (event.key.toLowerCase() === 'r') goNextRisk();
      if (event.key === 'ArrowLeft') goPrevious();
      if (event.key === 'ArrowRight') goNext();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [confirmAndNext, goNext, goNextRisk, goPrevious]);

  if (!taskId) {
    return (
      <ReviewTaskQueuePage
        tasks={reviewTasks}
        loading={reviewTasksLoading}
        error={reviewTasksError}
        openTask={(id) => navigate(`/review/${encodeURIComponent(id)}`)}
        deleteTask={(id) => void handleDeleteReviewTask(id)}
        deletingTaskId={deletingTaskId}
        goImport={() => navigate('/import')}
      />
    );
  }
  if (loading) return <CenteredState title="正在加载校对任务" desc="正在读取导入结果和图片缓存。" />;
  if (error) return <CenteredState title={error} desc={`任务 ID：${taskId}`} action="返回导入识别" onAction={() => navigate('/import')} />;
  if (knowledgeDrafts.length > 0 && drafts.length === 0) {
    return (
      <KnowledgeReviewWorkbench
        drafts={knowledgeDrafts}
        saving={saving}
        saveError={saveError}
        saveResult={knowledgeSaveResult}
        updateDraft={updateKnowledgeDraft}
        setStatus={setKnowledgeStatus}
        save={handleSaveKnowledge}
        back={() => navigate('/review')}
      />
    );
  }
  if (drafts.length === 0) return <CenteredState title="暂无可校对数据" desc="该任务没有解析出题目，请先完成导入识别。" action="返回导入识别" onAction={() => navigate('/import')} />;

  const risks = currentDraft ? getRiskItems(currentDraft, duplicateQuestionIds, qualityConfig) : [];

  return (
    <section aria-label="校对工作台" className="flex h-full min-h-0 flex-col bg-[var(--color-bg)] text-[var(--color-text)]">
      <header className="z-20 shrink-0 border-b border-[var(--color-border)] bg-[var(--color-bg-card)] px-4 py-2">
        <div className="flex min-w-0 items-center gap-3">
          <button type="button" className={SOFT_BUTTON_CLASS} aria-label="返回任务列表" title="返回任务列表" onClick={() => navigate('/review')}><ChevronLeft size={14} className="sm:mr-1 sm:inline" /><span className="hidden sm:inline">任务列表</span></button>
          <div className="min-w-0">
            <h1 className="truncate text-base font-bold">题目校对</h1>
            <div className="text-[11px] text-[var(--color-text-muted)]">第 {currentIndex + 1} 题 · 已处理 {counts.confirmed + counts.discarded}/{counts.total}</div>
          </div>
          <div className="hidden h-1.5 min-w-24 flex-1 overflow-hidden rounded-full bg-[var(--color-bg-hover)] sm:block">
            <div className="h-full rounded-full bg-[var(--color-success)] transition-all" style={{ width: `${counts.total ? ((counts.confirmed + counts.discarded) / counts.total) * 100 : 0}%` }} />
          </div>
          <span className="hidden text-xs font-semibold text-[var(--color-danger)] md:inline">风险 {counts.risk}</span>
          <span className="hidden text-xs font-semibold text-[var(--color-success)] md:inline">已确认 {counts.confirmed}</span>
          <span
            title={serverDraftUpdatedAt?.toLocaleString()}
            className={`hidden items-center gap-1 text-[11px] lg:inline-flex ${serverDraftStatus === 'conflict' ? 'text-[var(--color-danger)]' : serverDraftStatus === 'offline' ? 'text-[var(--color-orange)]' : 'text-[var(--color-success)]'}`}
          >
            <Cloud size={12} />
            {serverDraftStatus === 'saving' && '保存中'}
            {serverDraftStatus === 'conflict' && '版本冲突'}
            {serverDraftStatus === 'offline' && '离线草稿'}
            {(serverDraftStatus === 'saved' || serverDraftStatus === 'idle') && '已自动保存'}
          </span>
          <div className="relative">
            <button type="button" className={SOFT_BUTTON_CLASS} aria-label="历史版本" title="历史版本" onClick={() => void handleToggleHistory()}><History size={15} /></button>
            {historyOpen && (
              <div className="absolute right-0 top-10 z-40 w-72 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-card)] p-2 shadow-xl">
                <div className="mb-2 px-1 text-xs font-bold">服务器草稿历史</div>
                {historyLoading && <div className="px-2 py-3 text-xs text-[var(--color-text-muted)]">正在读取...</div>}
                {!historyLoading && draftVersions.length === 0 && <div className="px-2 py-3 text-xs text-[var(--color-text-muted)]">暂无历史版本</div>}
                {!historyLoading && draftVersions.map((item) => (
                  <button type="button" key={item.version} className="flex w-full items-center justify-between rounded-md px-2 py-2 text-left text-xs hover:bg-[var(--color-bg-hover)] disabled:opacity-50" disabled={item.version === serverDraftVersion} onClick={() => void handleRestoreVersion(item.version)}>
                    <span className="font-semibold">v{item.version}{item.version === serverDraftVersion ? '（当前）' : ''}</span>
                    <span className="text-[var(--color-text-muted)]">{new Date(item.updated_at).toLocaleString()} · {item.state.drafts.length} 题</span>
                  </button>
                ))}
              </div>
            )}
          </div>
          <button type="button" className={`${PRIMARY_BUTTON_CLASS} inline-flex items-center gap-1.5`} onClick={() => void handleSubmitReview()} disabled={saving || counts.confirmed === 0} title={counts.confirmed === 0 ? '请先确认至少一道题' : `提交 ${counts.confirmed} 道已确认题目`}>
            <Send size={14} />{saving ? '提交中...' : `提交（${counts.confirmed}）`}
          </button>
        </div>
        {serverDraftStatus === 'conflict' && (
          <div className="mt-2 flex flex-wrap items-center gap-3 border-t border-[var(--color-danger)] pt-2 text-xs text-[var(--color-danger)]">
            <TriangleAlert size={14} />
            <span className="font-semibold">另一页面已经保存了更新版本。为避免覆盖，当前页面已暂停服务器自动保存。</span>
            {serverConflict && <button type="button" className="ml-auto rounded-md bg-white px-3 py-1.5 font-bold shadow-sm" onClick={handleLoadServerConflict}>加载服务器 v{serverConflict.version}</button>}
          </div>
        )}
        {(saveError || saveResult) && (
          <div className={`mt-2 rounded-md border px-3 py-2 text-xs ${saveError ? 'border-[var(--color-danger)] bg-[var(--color-danger-soft)] text-[var(--color-danger)]' : 'border-emerald-200 bg-emerald-50 text-emerald-700'}`}>
            {saveError || `提交完成：已入库 ${saveResult?.saved_count || 0} 题，跳过 ${saveResult?.skipped_count || 0} 题，失败 ${saveResult?.failed_count || 0} 题。`}
          </div>
        )}
      </header>

      <section className={`relative grid min-h-0 flex-1 overflow-hidden ${toolsOpen ? 'xl:grid-cols-[220px_minmax(0,1fr)_300px]' : 'lg:grid-cols-[220px_minmax(0,1fr)]'}`}>
        <ReviewQueueSidebar
          counts={counts}
          currentIndex={currentIndex}
          filteredDrafts={filteredDrafts}
          getRisks={(draft) => getRiskItems(draft, duplicateQuestionIds, qualityConfig)}
          onSelect={setCurrentIndex}
          questionQuery={questionQuery}
          queue={queue}
          setQuestionQuery={setQuestionQuery}
          setQueue={setQueue}
          statusLabel={statusLabel}
          typeLabels={TYPE_LABELS}
        />

        <section className="min-w-0 overflow-y-auto bg-[var(--color-bg)] p-3">
          <div className="sticky top-0 z-10 mb-3 flex flex-wrap items-center gap-2 rounded-md border border-[var(--color-border)] bg-[var(--color-bg-card)] p-2 shadow-sm">
            <div className="flex rounded-md bg-[var(--color-bg-hover)] p-0.5">
              <WorkspaceViewButton active={workspaceView === 'edit'} label="编辑与预览" icon={<PencilLine size={14} />} onClick={() => setWorkspaceView('edit')} />
              <WorkspaceViewButton active={workspaceView === 'source'} label="原文" icon={<FileSearch size={14} />} onClick={() => setWorkspaceView('source')} />
            </div>
            <div className="h-5 w-px bg-[var(--color-border)]" />
            <button type="button" className={SOFT_BUTTON_CLASS} aria-label="上一题" title="上一题" onClick={goPrevious} disabled={currentIndex <= 0}><ChevronLeft size={15} /></button>
            <span className="px-1 text-xs font-bold text-[var(--color-text-secondary)]">第 {currentIndex + 1} / {drafts.length} 题</span>
            <button type="button" className={SOFT_BUTTON_CLASS} aria-label="下一题" title="下一题" onClick={goNext} disabled={currentIndex >= drafts.length - 1}><ChevronRight size={15} /></button>
            <button type="button" className={PRIMARY_BUTTON_CLASS} onClick={confirmAndNext}><CheckCircle2 size={15} className="mr-1 inline" />确认并下一题</button>
            <button type="button" className={SOFT_BUTTON_CLASS} onClick={handleSingleAiSuggestion} disabled={aiProcessing}><Sparkles size={15} className="mr-1 inline" />AI 建议</button>
            <button type="button" className={SOFT_BUTTON_CLASS} aria-label="恢复原稿" title="恢复原稿" onClick={restoreCurrent}><RotateCcw size={15} /></button>
            <button type="button" className={`${SOFT_BUTTON_CLASS} text-[var(--color-danger)]`} aria-label="丢弃此题" title="丢弃此题" onClick={() => updateStatus('discarded')}><Trash2 size={15} /></button>
            <button type="button" className={`${SOFT_BUTTON_CLASS} ml-auto inline-flex items-center gap-1.5`} onClick={() => setToolsOpen((value) => !value)}>
              {toolsOpen ? <PanelRightClose size={15} /> : <PanelRightOpen size={15} />}辅助工具
            </button>
          </div>
          <div className="mx-auto max-w-[1440px]">
            {risks.length > 0 && (
              <div className="mb-3 flex items-center gap-2 rounded-md border border-[var(--color-danger)] bg-[var(--color-danger-soft)] px-3 py-2 text-xs text-[var(--color-danger)]">
                <TriangleAlert size={14} className="shrink-0" />
                <b>请检查：</b><span className="truncate">{risks.map((risk) => risk.message).join('、')}</span>
                <button type="button" className="ml-auto shrink-0 font-semibold" onClick={goNextRisk}>下一风险题</button>
              </div>
            )}
            {workspaceView === 'edit' && currentDraft && <QualityChecklistPanel draft={currentDraft} original={currentOriginal} qualityConfig={qualityConfig} />}
            {workspaceView === 'edit' && currentDraft && (
              <EditorPanel
                draft={currentDraft}
                updateDraftAt={(patch) => updateDraftAt(currentIndex, patch)}
                insertFigureRequest={figureInsertRequest}
                onFigureInsertHandled={(requestId) => setFigureInsertQueue((queue) => queue[0]?.requestId === requestId ? queue.slice(1) : queue)}
                imageProcessRequest={imageProcessRequest}
                onImageProcessHandled={(requestId) => setImageProcessRequest((request) => request?.requestId === requestId ? null : request)}
                openImagePicker={() => setImagePickerOpen(true)}
              />
            )}
            {workspaceView === 'source' && <OriginalPreviewPanel draft={currentDraft} page={currentPage} pages={taskMeta.pageResults} warnings={taskMeta.warnings} />}
            {aiMessage && <div className="mt-3 rounded-md border border-[var(--color-border)] bg-[var(--color-bg-card)] p-3 text-xs text-[var(--color-text-secondary)]">{aiMessage}</div>}
            {aiSuggestion && <div className="mt-3"><SuggestionPanel suggestion={aiSuggestion} accept={acceptSuggestion} dismiss={() => setAiSuggestion(null)} /></div>}
          </div>
        </section>

        {toolsOpen && (
          <aside className="absolute inset-y-0 right-0 z-30 w-[min(320px,92vw)] space-y-3 overflow-y-auto border-l border-[var(--color-border)] bg-[var(--color-bg-card)] p-3 shadow-xl xl:static xl:w-auto xl:shadow-none">
            <div className="flex items-center justify-between border-b border-[var(--color-border)] pb-2">
              <h2 className="text-sm font-bold">辅助工具</h2>
              <button type="button" className={SOFT_BUTTON_CLASS} aria-label="关闭辅助工具" title="关闭辅助工具" onClick={() => setToolsOpen(false)}><PanelRightClose size={15} /></button>
            </div>
            <QualityRuleSettingsPanel config={qualityConfig} setConfig={setQualityConfig} />
            <ChangeReviewPanel draft={currentDraft} original={currentOriginal} restoreField={(field) => {
              if (!currentOriginal) return;
              const originalValue = currentOriginal[field];
              updateCurrentField(field, originalValue && typeof originalValue === 'object' ? JSON.parse(JSON.stringify(originalValue)) : originalValue);
            }} />
            <BatchPanel
              aiProcessing={aiProcessing}
              cacheMessage={cacheMessage}
              confirmQueue={() => {
                const indexes = new Set(filteredDrafts.map((item) => item.index));
                setDrafts((prev) => prev.map((draft, index) => indexes.has(index) && draft.status !== 'discarded' ? { ...draft, status: 'confirmed' } : draft));
              }}
              confirmClean={() => setDrafts((prev) => prev.map((draft) => draft.status !== 'discarded' && getRiskItems(draft, duplicateQuestionIds, qualityConfig).length === 0 ? { ...draft, status: 'confirmed' } : draft))}
              batchAnalysis={handleBatchAnalysis}
              batchMetadata={handleBatchMetadata}
              fastLatexCleanup={handleFastLatexCleanup}
              exportJSON={handleExportJSON}
              clearCache={() => {
                if (!taskId) return;
                clearReviewCache(taskId);
                setCacheMessage('本地校对缓存已清除');
              }}
            />
          </aside>
        )}
      </section>
      {imagePickerOpen && (
        <div className="pointer-events-none fixed inset-0 z-[70] flex justify-end" role="dialog" aria-label="图片缓存">
          <section className="pointer-events-auto flex h-full w-full max-w-[420px] flex-col border-l border-[var(--color-border)] bg-[var(--color-bg-card)] shadow-2xl">
            <header className="flex items-center justify-between border-b border-[var(--color-border)] px-4 py-3">
              <div>
                <h2 className="text-sm font-bold">图片缓存</h2>
                <p className="mt-0.5 text-[11px] text-[var(--color-text-muted)]">点击图片，插入到当前光标位置。</p>
              </div>
              <button type="button" className={SOFT_BUTTON_CLASS} aria-label="关闭图片缓存" title="关闭图片缓存" onClick={() => setImagePickerOpen(false)}><X size={15} /></button>
            </header>
            <div className="min-h-0 flex-1 overflow-y-auto p-3">
              <ImageCachePanel assets={taskMeta.mediaAssets} draft={currentDraft} canUpload={Boolean(taskMeta.batchId)} uploading={imageUploading} copyText={copyText} copyImage={copyImage} attachAsset={attachAssetToCurrent} uploadImage={(file) => void handleUploadImageToCurrent(file)} processAsset={handleProcessImageForCurrent} copyMessage={copyMessage} />
            </div>
          </section>
        </div>
      )}
    </section>
  );
}

function WorkspaceViewButton({ active, label, icon, onClick }: { active: boolean; label: string; icon: ReactNode; onClick: () => void }) {
  return (
    <button type="button" className={`inline-flex items-center gap-1.5 rounded px-2.5 py-1.5 text-xs font-semibold ${active ? 'bg-white text-[var(--color-accent)] shadow-sm' : 'text-[var(--color-text-secondary)]'}`} onClick={onClick}>
      {icon}{label}
    </button>
  );
}

function ReviewTaskQueuePage({
  tasks,
  loading,
  error,
  openTask,
  deleteTask,
  deletingTaskId,
  goImport,
}: {
  tasks: ReviewTaskListItem[];
  loading: boolean;
  error: string | null;
  openTask: (taskId: string) => void;
  deleteTask: (taskId: string) => void;
  deletingTaskId: string | null;
  goImport: () => void;
}) {
  const questionTaskCount = tasks.filter((task) => task.task_type !== 'ai_generated_knowledge_review').length;
  const knowledgeTaskCount = tasks.length - questionTaskCount;
  const pendingItemCount = tasks.reduce((total, task) => total + (task.knowledge_count > 0 ? task.knowledge_count : task.question_count), 0);

  return (
    <section aria-label="校对任务概览" className="h-full overflow-y-auto bg-[#f3f6fa] px-3 py-3 text-[var(--color-text)] sm:px-5 sm:py-4">
      <div className="mx-auto max-w-[1280px]">
      <header className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-lg font-bold text-[#1d3148]">待校对任务</h1>
          <p className="mt-1 text-xs text-[var(--color-text-muted)]">确认后写入正式题库；未提交内容保留在校对区。</p>
        </div>
        <button type="button" className={PRIMARY_BUTTON_CLASS} onClick={goImport}>新建导入任务</button>
      </header>
      {!loading && !error && tasks.length > 0 && (
        <section className="mb-3 grid overflow-hidden rounded-lg border border-[var(--color-border)] bg-white sm:grid-cols-3 sm:divide-x sm:divide-[var(--color-border)]">
          <QueueMetric label="待校对对象" value={pendingItemCount} hint="题目与知识点合计" />
          <QueueMetric label="试题任务" value={questionTaskCount} hint="等待结构与答案核验" />
          <QueueMetric label="知识点任务" value={knowledgeTaskCount} hint="等待内容与层级核验" />
        </section>
      )}
      {loading && <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-card)] p-8 text-center text-sm">正在读取审核数据库...</div>}
      {error && <div className="rounded-lg border border-[var(--color-danger)] bg-[#fff0f0] p-8 text-center text-sm text-[var(--color-danger)]">{error}</div>}
      {!loading && !error && tasks.length === 0 && (
        <div className="rounded-lg border border-dashed border-[var(--color-border)] bg-[var(--color-bg-card)] p-10 text-center">
          <h2 className="text-base font-bold">暂无审核任务</h2>
          <p className="mt-2 text-sm text-[var(--color-text-secondary)]">从 AI 对话里送审后，这里会自动出现任务。</p>
        </div>
      )}
      {!loading && !error && tasks.length > 0 && (
        <div className="divide-y divide-[var(--color-border)] overflow-hidden rounded-lg border border-[var(--color-border)] bg-white shadow-sm">
          {tasks.map((task) => (
            <article key={task.task_id} className="grid gap-3 px-4 py-3 transition-colors hover:bg-[#f8fafc] sm:grid-cols-[minmax(0,1fr)_140px_180px_auto] sm:items-center">
                <div className="min-w-0">
                  <h2 className="truncate text-sm font-semibold text-[#263b52]">{task.title || task.batch_id || task.task_id}</h2>
                  <p className="mt-1 truncate text-xs text-[var(--color-text-muted)]">{task.source || task.batch_id}</p>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                    <span className="rounded bg-[#eff6ff] px-2 py-1 text-xs font-bold text-[var(--color-accent)]">
                      {task.task_type === 'ai_generated_knowledge_review' ? '知识点送审' : '试题送审'}
                    </span>
                    <span className="text-xs font-medium text-[var(--color-text-secondary)]">
                      {task.knowledge_count > 0 ? `${task.knowledge_count} 知识点` : `${task.question_count} 题`}
                    </span>
                </div>
                <p className="text-xs text-[var(--color-text-muted)]">更新 {new Date(task.updated_at).toLocaleString()}</p>
                <div className="flex shrink-0 gap-2 sm:justify-end">
                  <button type="button" className={PRIMARY_BUTTON_CLASS} onClick={() => openTask(task.task_id)}>打开校对</button>
                  <button
                    type="button"
                    className={`${SOFT_BUTTON_CLASS} text-[var(--color-danger)]`}
                    onClick={() => deleteTask(task.task_id)}
                    disabled={deletingTaskId === task.task_id}
                  >
                    {deletingTaskId === task.task_id ? '删除中...' : '删除任务'}
                  </button>
                </div>
            </article>
          ))}
        </div>
      )}
      </div>
    </section>
  );
}

function QueueMetric({ label, value, hint }: { label: string; value: number; hint: string }) {
  return (
    <div className="px-4 py-3">
      <p className="text-xs font-medium text-[var(--color-text-muted)]">{label}</p>
      <div className="mt-1 flex items-end justify-between gap-3">
        <strong className="text-lg font-bold text-[#1d3148]">{value}</strong>
        <span className="pb-0.5 text-xs text-[var(--color-text-secondary)]">{hint}</span>
      </div>
    </div>
  );
}

function KnowledgeReviewWorkbench({
  drafts,
  saving,
  saveError,
  saveResult,
  updateDraft,
  setStatus,
  save,
  back,
}: {
  drafts: KnowledgeReviewDraft[];
  saving: boolean;
  saveError: string | null;
  saveResult: SaveReviewedKnowledgeResponse | null;
  updateDraft: (index: number, patch: Partial<KnowledgeReviewDraft>) => void;
  setStatus: (index: number, status: KnowledgeReviewDraft['status']) => void;
  save: () => void;
  back: () => void;
}) {
  const [currentIndex, setCurrentIndex] = useState(0);
  const currentDraft = drafts[Math.min(currentIndex, Math.max(drafts.length - 1, 0))] ?? null;
  const confirmedCount = drafts.filter((draft) => draft.status === 'confirmed').length;
  const unfinishedCount = drafts.filter((draft) => draft.status === 'pending' || draft.status === 'modified').length;

  const submitKnowledge = () => {
    if (unfinishedCount > 0) {
      const confirmed = window.confirm(`还有 ${unfinishedCount} 个知识点尚未确认。本次只提交已确认的 ${confirmedCount} 个，是否继续？`);
      if (!confirmed) return;
    }
    save();
  };

  if (!currentDraft) {
    return <CenteredState title="暂无知识点草稿" desc="当前任务没有可校对的知识点。" action="返回队列" onAction={back} />;
  }

  const risks = getKnowledgeRisks(currentDraft);

  return (
    <section aria-label="导入校对" className="flex h-screen min-h-0 flex-col bg-[var(--color-bg)] text-[var(--color-text)]">
      <header className="shrink-0 border-b border-[var(--color-border)] bg-[var(--color-bg-card)] px-4 py-2.5">
        <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-base font-bold">知识点校对中心</h1>
          <p className="mt-1 text-sm text-[var(--color-text-secondary)]">左侧修改，右侧实时渲染；确认后才写入正式知识点库。</p>
        </div>
        <div className="flex gap-2">
          <button type="button" className={SOFT_BUTTON_CLASS} onClick={back}>返回队列</button>
          <button type="button" className={`${PRIMARY_BUTTON_CLASS} inline-flex items-center gap-1.5`} onClick={submitKnowledge} disabled={saving || confirmedCount === 0}>
            <Send size={14} />{saving ? '提交中...' : `提交校对（${confirmedCount}）`}
          </button>
        </div>
        </div>
        <div className="mt-3 flex flex-wrap gap-2 text-xs">
          <Stat label="知识点" value={drafts.length} />
          <Stat label="已确认" value={drafts.filter((draft) => draft.status === 'confirmed').length} tone="success" />
        </div>
        {saveError && <div className="mt-3 rounded-lg border border-[var(--color-danger)] bg-[#fff0f0] p-3 text-sm text-[var(--color-danger)]">{saveError}</div>}
        {saveResult && <div className="mt-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-card)] p-3 text-sm">已保存 {saveResult.saved_count} 个，跳过 {saveResult.skipped_count} 个，失败 {saveResult.failed_count} 个。</div>}
      </header>

      <section className="grid min-h-0 flex-1 grid-cols-[220px_minmax(0,1fr)_minmax(300px,0.8fr)] overflow-hidden">
        <aside className="overflow-y-auto border-r border-[var(--color-border)] bg-[var(--color-bg-card)] p-3">
          <div className="mb-2 text-xs font-bold text-[var(--color-text-muted)]">待校对知识点</div>
          <div className="space-y-2">
            {drafts.map((draft, index) => (
              <button
                key={draft.draft_id}
                type="button"
                onClick={() => setCurrentIndex(index)}
                className={`w-full rounded-md border p-3 text-left ${index === currentIndex ? 'border-[var(--color-accent)] bg-[#eef5ff]' : 'border-[var(--color-border)] bg-[var(--color-bg)]'}`}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="text-xs font-bold text-[var(--color-accent)]">{index + 1}</span>
                  <span className="rounded-full bg-[var(--color-bg-hover)] px-2 py-0.5 text-[11px]">{statusLabel(draft.status)}</span>
                </div>
                <div className="mt-2 line-clamp-2 text-xs font-semibold text-[var(--color-text)]">{draft.topic3_name || '未命名知识点'}</div>
                <div className="mt-1 truncate text-[11px] text-[var(--color-text-muted)]">{draft.topic3_id || draft.draft_id}</div>
              </button>
            ))}
          </div>
        </aside>

        <section className="min-h-0 overflow-y-auto p-3">
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-card)] p-3">
            <div className="mb-4 flex items-start justify-between gap-3">
              <div>
                <div className="text-xs font-bold text-[var(--color-accent)]">修改区 · 知识点 {currentIndex + 1}</div>
                <h2 className="mt-1 text-base font-bold">{currentDraft.topic3_name || '未命名知识点'}</h2>
              </div>
              <span className="rounded-full bg-[var(--color-bg-hover)] px-2 py-1 text-xs">{statusLabel(currentDraft.status)}</span>
            </div>
            {risks.length > 0 && <div className="mb-3 rounded-md bg-[#fff7ed] p-2 text-xs text-[#c2410c]">{risks.join('；')}</div>}
            <div className="grid gap-3 md:grid-cols-2">
              <TextField label="知识点 ID" value={currentDraft.topic3_id} onChange={(value) => updateDraft(currentIndex, { topic3_id: value })} />
              <TextField label="知识点名称" value={currentDraft.topic3_name} onChange={(value) => updateDraft(currentIndex, { topic3_name: value })} />
              <TextField label="一级章节 ID" value={currentDraft.topic1_id} onChange={(value) => updateDraft(currentIndex, { topic1_id: value })} />
              <TextField label="一级章节" value={currentDraft.topic1_name} onChange={(value) => updateDraft(currentIndex, { topic1_name: value })} />
              <TextField label="二级章节 ID" value={currentDraft.topic2_id} onChange={(value) => updateDraft(currentIndex, { topic2_id: value })} />
              <TextField label="二级章节" value={currentDraft.topic2_name} onChange={(value) => updateDraft(currentIndex, { topic2_name: value })} />
              <TextField label="来源章节" value={currentDraft.source_chapter} onChange={(value) => updateDraft(currentIndex, { source_chapter: value })} />
              <TextField label="标签" value={currentDraft.tags.join('、')} onChange={(value) => updateDraft(currentIndex, { tags: value.split(/[、,，]/).map((item) => item.trim()).filter(Boolean) })} />
            </div>
            <div className="mt-4 flex flex-wrap gap-2">
              <button type="button" className={PRIMARY_BUTTON_CLASS} onClick={() => setStatus(currentIndex, 'confirmed')}>确认</button>
              <button type="button" className={SOFT_BUTTON_CLASS} onClick={() => setStatus(currentIndex, 'pending')}>待改</button>
              <button type="button" className={SOFT_BUTTON_CLASS} onClick={() => setStatus(currentIndex, 'discarded')}>丢弃</button>
            </div>
            <div className="mt-4 grid gap-3">
              <TextAreaField label="标准定义" value={currentDraft.definition} onChange={(value) => updateDraft(currentIndex, { definition: value })} />
              <TextAreaField label="核心公式" value={currentDraft.formula} onChange={(value) => updateDraft(currentIndex, { formula: value })} />
              <TextAreaField label="核心摘要" value={currentDraft.key_summary} onChange={(value) => updateDraft(currentIndex, { key_summary: value })} />
              <TextAreaField label="易错点" value={currentDraft.error_prone} onChange={(value) => updateDraft(currentIndex, { error_prone: value })} />
              <TextAreaField label="例题解析" value={currentDraft.example_analysis} onChange={(value) => updateDraft(currentIndex, { example_analysis: value })} />
            </div>
          </div>
        </section>

        <aside className="min-h-0 overflow-y-auto border-l border-[var(--color-border)] bg-[var(--color-bg-card)] p-3">
          <KnowledgeDraftPreview draft={currentDraft} />
        </aside>
      </section>
    </section>
  );
}

function KnowledgeDraftPreview({ draft }: { draft: KnowledgeReviewDraft }) {
  return (
    <article className="space-y-4">
      <div>
        <div className="text-xs font-bold text-[var(--color-accent)]">渲染区</div>
        <h2 className="mt-1 text-lg font-bold">{draft.topic3_name || '未命名知识点'}</h2>
        <div className="mt-2 flex flex-wrap gap-2 text-xs text-[var(--color-text-secondary)]">
          {draft.topic1_name && <span className="pv-chip">{draft.topic1_name}</span>}
          {draft.topic2_name && <span className="pv-chip">{draft.topic2_name}</span>}
          {draft.source_chapter && <span className="pv-chip">{draft.source_chapter}</span>}
        </div>
      </div>
      <KnowledgePreviewSection title="标准定义" text={draft.definition} />
      <KnowledgePreviewSection title="核心公式" text={draft.formula} />
      <KnowledgePreviewSection title="核心摘要" text={draft.key_summary} />
      <KnowledgePreviewSection title="易错点" text={draft.error_prone} />
      <KnowledgePreviewSection title="例题解析" text={draft.example_analysis} />
      {draft.tags.length > 0 && (
        <section>
          <div className="mb-2 text-xs font-bold text-[var(--color-text-muted)]">标签</div>
          <div className="flex flex-wrap gap-2">{draft.tags.map((tag) => <span key={tag} className="pv-chip">{tag}</span>)}</div>
        </section>
      )}
    </article>
  );
}

function KnowledgePreviewSection({ title, text }: { title: string; text: string }) {
  if (!text.trim()) return null;
  return (
    <section>
      <div className="mb-2 text-xs font-bold text-[var(--color-text-muted)]">{title}</div>
      <div className="rounded-md bg-[var(--color-bg)] p-3 text-sm leading-7">
        <LatexRenderer text={text} />
      </div>
    </section>
  );
}

function TextField({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) {
  return (
    <label className="grid gap-1 text-xs font-semibold text-[var(--color-text-secondary)]">
      {label}
      <input className={INPUT_CLASS} value={value} onChange={(event) => onChange(event.target.value)} />
    </label>
  );
}

function TextAreaField({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) {
  return (
    <div className="grid gap-1 text-xs font-semibold text-[var(--color-text-secondary)]">
      <div className="flex items-center justify-between gap-2">
        <span>{label}</span>
        <button type="button" className={SOFT_BUTTON_CLASS} onClick={() => onChange(appendTableTemplate(value))}>插入表格</button>
      </div>
      <textarea rows={3} className={TEXTAREA_CLASS} value={value} onChange={(event) => onChange(event.target.value)} />
      {value.trim() && <div className="rounded-md bg-[var(--color-bg)] p-2 font-normal"><LatexRenderer text={value} /></div>}
    </div>
  );
}

function EditorPanel({ draft, updateDraftAt, insertFigureRequest, onFigureInsertHandled, imageProcessRequest, onImageProcessHandled, openImagePicker }: {
  draft: ReviewQuestionDraft;
  updateDraftAt: (patch: Partial<ReviewQuestionDraft>) => void;
  insertFigureRequest: FigureInsertRequest | null;
  onFigureInsertHandled: (requestId: number) => void;
  imageProcessRequest: ImageProcessApplyRequest | null;
  onImageProcessHandled: (requestId: number) => void;
  openImagePicker: () => void;
}) {
  const [localDraft, setLocalDraft] = useState(draft);
  const [editorOpen, setEditorOpen] = useState(false);
  const localDraftRef = useRef(draft);
  const dirtyRef = useRef(false);

  useEffect(() => {
    localDraftRef.current = localDraft;
  }, [localDraft]);

  useEffect(() => {
    // Parent updates are the persisted source of truth. While the user is
    // typing, keep their local document intact; once it has been published,
    // accept external changes such as AI suggestions and format actions.
    if (draft.question_id !== localDraftRef.current.question_id || !dirtyRef.current) {
      localDraftRef.current = draft;
      setLocalDraft(draft);
    }
  }, [draft]);

  const publishLocalDraft = useCallback(() => {
    if (!dirtyRef.current) return;
    dirtyRef.current = false;
    updateDraftAt(localDraftRef.current);
  }, [updateDraftAt]);

  useEffect(() => {
    if (!dirtyRef.current) return;
    const timer = window.setTimeout(publishLocalDraft, 350);
    return () => window.clearTimeout(timer);
  }, [localDraft, publishLocalDraft]);

  useEffect(() => () => publishLocalDraft(), [draft.question_id, publishLocalDraft]);

  const mergeFigureIntoLocalDraft = useCallback((figure: Figure) => {
    setLocalDraft((current) => {
      if (current.figures.some((item) => item.fig_uuid === figure.fig_uuid)) return current;
      const updated = { ...current, figures: [...current.figures, figure] };
      updated.figureIssues = computeFigureIssues(updated);
      if (updated.status === 'pending') updated.status = 'modified';
      dirtyRef.current = true;
      localDraftRef.current = updated;
      return updated;
    });
  }, []);

  useEffect(() => {
    if (!insertFigureRequest) return;
    const { figure } = insertFigureRequest;
    const reviewFigure: Figure = {
      fig_uuid: figure.fig_uuid,
      local_path: figure.local_path,
      ...(figure.display_scale === null || figure.display_scale === undefined ? {} : { display_scale: figure.display_scale }),
      ...(figure.display_align ? { display_align: figure.display_align } : {}),
    };
    mergeFigureIntoLocalDraft(reviewFigure);
  }, [insertFigureRequest, mergeFigureIntoLocalDraft]);

  const completeFigureInsert = useCallback((requestId: number) => {
    if (insertFigureRequest?.requestId === requestId) {
      mergeFigureIntoLocalDraft({
        fig_uuid: insertFigureRequest.figure.fig_uuid,
        local_path: insertFigureRequest.figure.local_path,
        ...(insertFigureRequest.figure.display_scale === null || insertFigureRequest.figure.display_scale === undefined ? {} : { display_scale: insertFigureRequest.figure.display_scale }),
        ...(insertFigureRequest.figure.display_align ? { display_align: insertFigureRequest.figure.display_align } : {}),
      });
    }
    onFigureInsertHandled(requestId);
  }, [insertFigureRequest, mergeFigureIntoLocalDraft, onFigureInsertHandled]);

  useEffect(() => {
    if (!imageProcessRequest || imageProcessRequest.questionId !== localDraftRef.current.question_id) return;
    setLocalDraft((current) => {
      const updated = applyImageProcessToDraft(current, imageProcessRequest);
      updated.figureIssues = computeFigureIssues(updated);
      if (updated.status === 'pending') updated.status = 'modified';
      dirtyRef.current = true;
      localDraftRef.current = updated;
      return updated;
    });
    onImageProcessHandled(imageProcessRequest.requestId);
  }, [imageProcessRequest, onImageProcessHandled]);

  const updateLocalDraft = useCallback((patch: Partial<ReviewQuestionDraft>) => {
    dirtyRef.current = true;
    setLocalDraft((current) => {
      const updated = { ...current, ...patch };
      updated.title = normalizeShortInlineDisplayMath(updated.title);
      updated.answer = normalizeShortInlineDisplayMath(updated.answer);
      updated.analysis = normalizeShortInlineDisplayMath(updated.analysis);
      updated.options = normalizeOptions(updated.options);
      updated.figureIssues = computeFigureIssues(updated);
      if (updated.status === 'pending') updated.status = 'modified';
      return updated;
    });
  }, []);

  return (
    <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-card)] p-3">
      <div className="mb-3 flex flex-wrap items-center gap-2 border-b border-[var(--color-border)] pb-3">
        <div className="mr-auto">
          <h2 className="text-sm font-bold">整题编辑</h2>
          <p className="mt-0.5 text-[11px] text-[var(--color-text-muted)]">题干、选项、图片、答案和解析连续编辑；选中图片可移动、对齐、缩放或删除。</p>
        </div>
        <button type="button" className={`${SOFT_BUTTON_CLASS} inline-flex items-center gap-1.5`} onClick={openImagePicker}><ImagePlus size={14} />新增图片</button>
        <button type="button" className={SOFT_BUTTON_CLASS} onClick={() => updateLocalDraft(buildSafeQuestionPatch(localDraft))} title="整理换行、行尾空格、选项编号和首尾空白，不改写题意">规范格式</button>
      </div>
      {editorOpen ? (
        <Suspense fallback={<div className="min-h-72 rounded-md border border-dashed border-[var(--color-border)] bg-[var(--color-bg)] p-4 text-sm text-[var(--color-text-muted)]">正在加载整题编辑器…</div>}>
          <QuestionLiveEditor
            question={localDraft as unknown as Question}
            onChange={(patch) => {
              const { editor_document: _editorDocument, ...reviewPatch } = patch;
              if (Object.keys(reviewPatch).length > 0) updateLocalDraft(reviewPatch as Partial<ReviewQuestionDraft>);
            }}
            compact={false}
            showPreview
            showHeader={false}
            showImageManager={false}
            showImageToolbarButton={false}
            syncDocument={false}
            insertFigureRequest={insertFigureRequest}
            onFigureInsertHandled={completeFigureInsert}
            onRequestImage={openImagePicker}
          />
        </Suspense>
      ) : (
        <div className="rounded-md border border-dashed border-[var(--color-border)] bg-[var(--color-bg)] p-4">
          <p className="text-sm text-[var(--color-text-secondary)]">整题编辑器会在开始编辑时加载，避免浏览审核任务时下载不需要的富文本功能。</p>
          <button type="button" className={`${PRIMARY_BUTTON_CLASS} mt-3`} onClick={() => setEditorOpen(true)}>开始整题编辑</button>
        </div>
      )}
      <details className="mt-3 border-t border-[var(--color-border)] pt-3">
        <summary className="cursor-pointer text-xs font-semibold text-[var(--color-text-secondary)]">题型、知识点与来源</summary>
        <div className="mt-2 grid gap-2 sm:grid-cols-2">
          <Field label="题型"><select className={INPUT_CLASS} value={localDraft.question_type} onChange={(event) => updateLocalDraft({ question_type: event.target.value })}>{TYPE_OPTIONS.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select></Field>
          <Field label="难度"><input className={INPUT_CLASS} value={localDraft.difficulty ?? ''} onChange={(event) => updateLocalDraft({ difficulty: event.target.value ? Number(event.target.value) : null })} /></Field>
          <Field label="知识点"><input className={INPUT_CLASS} value={localDraft.knowledge_point} onChange={(event) => updateLocalDraft({ knowledge_point: event.target.value })} /></Field>
          <Field label="来源"><input className={INPUT_CLASS} value={localDraft.source} onChange={(event) => updateLocalDraft({ source: event.target.value })} /></Field>
          <div className="sm:col-span-2"><Field label="标签"><input className={INPUT_CLASS} value={localDraft.tags.join('、')} onChange={(event) => updateLocalDraft({ tags: event.target.value.split(/[、,，]/).map((item) => item.trim()).filter(Boolean) })} /></Field></div>
        </div>
      </details>
    </div>
  );
}

function QualityChecklistPanel({ draft, original, qualityConfig }: { draft: ReviewQuestionDraft; original: ReviewQuestionDraft | null; qualityConfig: QuestionQualityRuleConfig }) {
  const isChoice = draft.question_type === 'single_choice' || draft.question_type === 'multi_choice';
  const qualityIssues = analyzeQuestionQuality(draft, { requireKnowledge: true, requireSource: true, config: qualityConfig });
  const qualityScore = scoreQuestionQuality(qualityIssues, qualityConfig);
  const items = [
    { label: '题干', passed: Boolean(draft.title.trim()) },
    { label: '选项', passed: !isChoice || draft.options.length >= 2 },
    { label: '答案', passed: Boolean(draft.answer.trim()) },
    { label: '知识点', passed: Boolean(draft.knowledge_point.trim()) },
    { label: '图片引用', passed: draft.figureIssues.length === 0 },
    { label: '来源', passed: Boolean(draft.source.trim()) },
  ];
  const passedCount = items.filter((item) => item.passed).length;
  const changedCount = getChangedReviewFields(original, draft).length;
  return (
    <div className="mb-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-card)] p-3">
      <div className="flex items-center justify-between gap-3">
        <div>
          <div className="text-xs font-bold text-[var(--color-text)]">字段完整度 {passedCount}/{items.length}</div>
          <div className="mt-0.5 text-[11px] text-[var(--color-text-muted)]">与识别原稿相比已修改 {changedCount} 个字段</div>
        </div>
        <div className="flex items-center gap-2">
          <div className="h-1.5 w-24 overflow-hidden rounded-full bg-[var(--color-bg-hover)]">
            <div className="h-full rounded-full" style={{ width: `${qualityScore}%`, background: qualityScore >= 85 ? 'var(--color-success)' : qualityScore >= 60 ? 'var(--color-orange)' : 'var(--color-danger)' }} />
          </div>
          <span className="text-sm font-black" style={{ color: qualityScore >= 85 ? 'var(--color-success)' : qualityScore >= 60 ? 'var(--color-orange)' : 'var(--color-danger)' }}>{qualityScore} 分</span>
        </div>
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        {items.map((item) => (
          <span key={item.label} className={`inline-flex items-center gap-1 rounded-full px-2 py-1 text-[11px] font-semibold ${item.passed ? 'bg-[var(--color-green-light)] text-[var(--color-green)]' : 'bg-[var(--color-danger-soft)] text-[var(--color-danger)]'}`}>
            {item.passed ? <CheckCircle2 size={11} /> : <TriangleAlert size={11} />}{item.label}
          </span>
        ))}
      </div>
    </div>
  );
}

function QualityRuleSettingsPanel({ config, setConfig }: { config: QuestionQualityRuleConfig; setConfig: (config: QuestionQualityRuleConfig) => void }) {
  const rules = Object.entries(QUESTION_QUALITY_RULE_LABELS) as Array<[QuestionQualityCode, string]>;
  const updateEnabled = (code: QuestionQualityCode, enabled: boolean) => {
    setConfig({ ...config, enabled: { ...config.enabled, [code]: enabled } });
  };
  return (
    <details className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-3">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-2 text-sm font-bold">
        <span>质检规则</span>
        <span className="text-[10px] font-normal text-[var(--color-text-muted)]">可按任务习惯调整</span>
      </summary>
      <label className="mt-3 flex items-center justify-between gap-3 text-xs text-[var(--color-text-secondary)]">
        <span>选择题最少选项数</span>
        <input
          type="number"
          min={1}
          max={8}
          value={config.minimumChoiceOptions ?? 2}
          onChange={(event) => setConfig({ ...config, minimumChoiceOptions: Math.max(1, Math.min(8, Number(event.target.value) || 2)) })}
          className="w-16 rounded border border-[var(--color-border)] bg-[var(--color-bg-card)] px-2 py-1 text-center"
        />
      </label>
      <div className="mt-3 max-h-72 space-y-1 overflow-y-auto pr-1">
        {rules.map(([code, label]) => (
          <div key={code} className="flex items-center gap-2 rounded-md px-1.5 py-1.5 hover:bg-[var(--color-bg-hover)]">
            <input type="checkbox" checked={config.enabled?.[code] !== false} onChange={(event) => updateEnabled(code, event.target.checked)} />
            <span className="min-w-0 flex-1 text-[11px] text-[var(--color-text-secondary)]">{label}</span>
            <select
              value={config.severity?.[code] ?? ''}
              onChange={(event) => {
                const value = event.target.value;
                const severity = { ...config.severity };
                if (value) severity[code] = value as QuestionQualitySeverity;
                else delete severity[code];
                setConfig({ ...config, severity });
              }}
              className="rounded border border-[var(--color-border)] bg-[var(--color-bg-card)] px-1 py-0.5 text-[10px]"
              aria-label={`${label}严重级别`}
            >
              <option value="">默认</option>
              <option value="danger">阻断</option>
              <option value="warning">警告</option>
              <option value="suggestion">建议</option>
            </select>
          </div>
        ))}
      </div>
      <button type="button" className={`${SOFT_BUTTON_CLASS} mt-3 w-full`} onClick={() => setConfig({})}>恢复默认规则</button>
    </details>
  );
}

function OriginalPreviewPanel({ draft, page, pages, warnings }: { draft: ReviewQuestionDraft | null; page: ReviewPageResult | null; pages: ReviewPageResult[]; warnings: string[] }) {
  const orderedPages = useMemo(
    () => [...pages].filter((item) => item.page_no).sort((a, b) => Number(a.page_no) - Number(b.page_no)),
    [pages],
  );
  const [selectedPageNo, setSelectedPageNo] = useState<number | null>(page?.page_no ?? null);
  const [zoom, setZoom] = useState(1);
  const [naturalSize, setNaturalSize] = useState({ width: 0, height: 0 });

  useEffect(() => {
    setSelectedPageNo(page?.page_no ?? null);
    setZoom(1);
  }, [draft?.question_id, page?.page_no]);

  const selectedPage = orderedPages.find((item) => item.page_no === selectedPageNo) ?? page;
  const selectedPageIndex = orderedPages.findIndex((item) => item.page_no === selectedPage?.page_no);
  const image = fileUrl(selectedPage?.page_image_path);
  const matchingRegion = selectedPage?.regions?.find((region) => (
    (draft?.source_region_id && region.region_id === draft.source_region_id)
    || region.question_id === draft?.question_id
  ));
  const bbox = selectedPage?.page_no === draft?.source_page
    ? (draft?.source_bbox ?? matchingRegion?.bbox ?? null)
    : null;
  const imageWidth = Number(selectedPage?.image_width || naturalSize.width || 0);
  const imageHeight = Number(selectedPage?.image_height || naturalSize.height || 0);
  const regionStyle = useMemo(() => {
    if (!bbox) return null;
    const [x, y, width, height] = bbox;
    const normalized = Math.max(x, y, width, height) <= 1;
    if (!normalized && (!imageWidth || !imageHeight)) return null;
    return {
      left: `${(normalized ? x : x / imageWidth) * 100}%`,
      top: `${(normalized ? y : y / imageHeight) * 100}%`,
      width: `${(normalized ? width : width / imageWidth) * 100}%`,
      height: `${(normalized ? height : height / imageHeight) * 100}%`,
    };
  }, [bbox, imageHeight, imageWidth]);

  const movePage = (offset: number) => {
    if (selectedPageIndex < 0) return;
    const next = orderedPages[selectedPageIndex + offset];
    if (next?.page_no) setSelectedPageNo(next.page_no);
  };

  return (
    <div>
      <div className="flex items-center justify-between gap-2">
        <div>
          <h2 className="text-sm font-bold">原文对照</h2>
          <div className="mt-0.5 text-[10px] text-[var(--color-text-muted)]">
            {selectedPage?.page_no ? `第 ${selectedPage.page_no} 页` : '未定位页码'}
            {draft?.source_region_id ? ` · 区域 ${draft.source_region_id}` : ''}
          </div>
        </div>
        <div className="flex items-center gap-1">
          <button type="button" className={SOFT_BUTTON_CLASS} aria-label="上一页" title="上一页" disabled={selectedPageIndex <= 0} onClick={() => movePage(-1)}><ChevronLeft size={13} /></button>
          <button type="button" className={SOFT_BUTTON_CLASS} aria-label="下一页" title="下一页" disabled={selectedPageIndex < 0 || selectedPageIndex >= orderedPages.length - 1} onClick={() => movePage(1)}><ChevronRight size={13} /></button>
        </div>
      </div>
      {warnings.length > 0 && <div className="mt-2 text-xs text-[var(--color-danger)]">{warnings.slice(0, 2).join('；')}</div>}
      {image ? (
        <>
          <div className="mt-2 flex items-center gap-1 text-[11px] text-[var(--color-text-muted)]">
            <button type="button" className={SOFT_BUTTON_CLASS} aria-label="缩小" title="缩小" onClick={() => setZoom((value) => Math.max(0.65, value - 0.2))}><ZoomOut size={13} /></button>
            <button type="button" className={SOFT_BUTTON_CLASS} onClick={() => setZoom(1)}>{Math.round(zoom * 100)}%</button>
            <button type="button" className={SOFT_BUTTON_CLASS} aria-label="放大" title="放大" onClick={() => setZoom((value) => Math.min(2.4, value + 0.2))}><ZoomIn size={13} /></button>
            <a className={`${SOFT_BUTTON_CLASS} ml-auto inline-flex items-center`} href={image} target="_blank" rel="noreferrer" title="新窗口打开"><ExternalLink size={13} /></a>
          </div>
          <div className="mt-2 max-h-[calc(100vh-260px)] overflow-auto rounded-md border border-[var(--color-border)] bg-white">
            <div className="relative origin-top-left transition-[width]" style={{ width: `${zoom * 100}%` }}>
              <img
                src={image}
                alt={`原文第 ${selectedPage?.page_no ?? '-'} 页`}
                className="block h-auto w-full"
                onLoad={(event) => setNaturalSize({ width: event.currentTarget.naturalWidth, height: event.currentTarget.naturalHeight })}
              />
              {regionStyle && (
                <div
                  className="pointer-events-none absolute border-2 border-[var(--color-danger)] bg-red-400/15 shadow-[0_0_0_2px_rgba(255,255,255,0.8)]"
                  style={regionStyle}
                  title="当前题原文区域"
                />
              )}
            </div>
          </div>
          {draft?.source_page === selectedPage?.page_no && !regionStyle && (
            <div className="mt-2 text-[10px] text-[var(--color-text-muted)]">已定位到原文页；当前识别结果暂未提供区域坐标。</div>
          )}
        </>
      ) : <div className="mt-3 rounded-md border border-dashed border-[var(--color-border)] p-3 text-xs text-[var(--color-text-muted)]">{draft?.raw_text || '当前题没有可定位的页图。'}</div>}
    </div>
  );
}

function ChangeReviewPanel({
  draft,
  original,
  restoreField,
}: {
  draft: ReviewQuestionDraft | null;
  original: ReviewQuestionDraft | null;
  restoreField: (field: keyof ReviewQuestionDraft) => void;
}) {
  const changedFields = getChangedReviewFields(original, draft);
  return (
    <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-3">
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-sm font-bold">原稿差异</h2>
        <span className="rounded-full bg-[var(--color-bg-hover)] px-2 py-0.5 text-[11px] text-[var(--color-text-muted)]">{changedFields.length} 处</span>
      </div>
      {changedFields.length === 0 ? (
        <div className="mt-3 flex items-center gap-2 rounded-md bg-[var(--color-green-light)] p-2 text-xs font-semibold text-[var(--color-green)]"><CheckCircle2 size={14} />当前内容与识别原稿一致</div>
      ) : (
        <div className="mt-3 space-y-2">
          {changedFields.map((field) => (
            <details key={field} className="group rounded-md border border-[var(--color-border)] bg-[var(--color-bg-card)]">
              <summary className="flex cursor-pointer list-none items-center justify-between gap-2 px-2.5 py-2 text-xs font-semibold text-[var(--color-text-secondary)]">
                <span>{REVIEW_FIELD_LABELS[field] ?? field}</span><span className="text-[10px] text-[var(--color-accent)]">查看差异</span>
              </summary>
              <div className="border-t border-[var(--color-border)] p-2.5">
                <ChangeValue before={displayReviewValue(original?.[field])} after={displayReviewValue(draft?.[field])} />
                <button type="button" className={`${SOFT_BUTTON_CLASS} mt-2 w-full`} onClick={() => restoreField(field)}>仅恢复此字段</button>
              </div>
            </details>
          ))}
        </div>
      )}
    </div>
  );
}

function ChangeValue({ before, after }: { before: string; after: string }) {
  let prefix = 0;
  while (prefix < before.length && prefix < after.length && before[prefix] === after[prefix]) prefix += 1;
  let suffix = 0;
  while (suffix < before.length - prefix && suffix < after.length - prefix && before[before.length - 1 - suffix] === after[after.length - 1 - suffix]) suffix += 1;
  const beforeChanged = before.slice(prefix, before.length - suffix || before.length);
  const afterChanged = after.slice(prefix, after.length - suffix || after.length);
  const start = before.slice(Math.max(0, prefix - 36), prefix);
  const end = suffix ? before.slice(before.length - suffix, Math.min(before.length, before.length - suffix + 36)) : '';
  return (
    <div className="space-y-2 text-[11px] leading-5">
      <div><div className="mb-1 font-bold text-[var(--color-text-muted)]">识别原稿</div><div className="max-h-24 overflow-auto whitespace-pre-wrap rounded bg-[var(--color-red-light)] p-2 text-[var(--color-text-secondary)]">{prefix > 36 && '…'}{start}<mark className="bg-[#fecaca] text-[#991b1b] line-through">{beforeChanged || '（删除）'}</mark>{end}{suffix > 36 && '…'}</div></div>
      <div><div className="mb-1 font-bold text-[var(--color-text-muted)]">当前版本</div><div className="max-h-24 overflow-auto whitespace-pre-wrap rounded bg-[var(--color-green-light)] p-2 text-[var(--color-text-secondary)]">{prefix > 36 && '…'}{start}<mark className="bg-[#bbf7d0] text-[#166534]">{afterChanged || '（删除）'}</mark>{end}{suffix > 36 && '…'}</div></div>
    </div>
  );
}

function ImageCachePanel({ assets, draft, canUpload, uploading, copyText, copyImage, attachAsset, uploadImage, processAsset, copyMessage }: {
  assets: ImportMediaAsset[];
  draft: ReviewQuestionDraft | null;
  canUpload: boolean;
  uploading: boolean;
  copyText: (text: string, message: string) => Promise<void>;
  copyImage: (asset: ImportMediaAsset) => Promise<void>;
  attachAsset: (asset: ImportMediaAsset) => void;
  uploadImage: (file: File) => void;
  processAsset: (asset: ImportMediaAsset, result: ImageProcessResult) => Promise<void>;
  copyMessage: string | null;
}) {
  const used = new Set(draft?.figures.map((figure) => figure.local_path) ?? []);
  const [processorAsset, setProcessorAsset] = useState<ImportMediaAsset | null>(null);
  return (
    <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-3">
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-sm font-bold">图片缓存区</h2>
        {copyMessage && <span className="text-xs text-[var(--color-success)]">{copyMessage}</span>}
      </div>
      <label className={`mt-3 flex cursor-pointer items-center justify-center rounded-md border border-dashed px-3 py-2 text-xs font-semibold ${canUpload ? 'border-[var(--color-accent)] bg-[#eef5ff] text-[var(--color-accent)]' : 'border-[var(--color-border)] text-[var(--color-text-muted)]'}`}>
        {uploading ? '正在上传图片...' : canUpload ? '上传图片并插入当前题' : '当前任务暂不支持上传图片'}
        <input
          type="file"
          accept="image/*"
          disabled={!canUpload || uploading || !draft}
          className="hidden"
          onChange={(event) => {
            const file = event.target.files?.[0];
            event.currentTarget.value = '';
            if (file) uploadImage(file);
          }}
        />
      </label>
      {assets.length === 0 && <div className="mt-3 rounded-md border border-dashed border-[var(--color-border)] p-3 text-xs text-[var(--color-text-muted)]">暂无缓存图片。导入识别提取到图片后会显示在这里。</div>}
      <div className="mt-3 grid grid-cols-2 gap-2">
        {assets.map((asset) => {
          const ref = `![fig:${asset.image_id || asset.filename || asset.relative_path}]`;
          return (
            <article key={asset.relative_path} className="overflow-hidden rounded-md border border-[var(--color-border)] bg-white">
              <button type="button" className="group relative block h-32 w-full bg-[#f7f9fc] p-2 hover:bg-[var(--color-accent-light)]" onClick={() => attachAsset(asset)} title="插入到当前光标位置">
                <img src={imageThumbnailUrl(asset.relative_path, 720) ?? ''} className="h-full w-full object-contain" />
                <span className="absolute inset-x-2 bottom-2 rounded bg-slate-900/75 px-2 py-1 text-[10px] font-semibold text-white opacity-0 transition-opacity group-hover:opacity-100">点击插入</span>
              </button>
              <div className="px-2 py-1.5">
                <div className="truncate text-[11px] text-[var(--color-text-secondary)]" title={asset.filename}>{asset.filename || asset.relative_path}</div>
                <div className="mt-1 flex items-center justify-between gap-1">
                  {used.has(asset.relative_path) ? <span className="text-[10px] font-semibold text-[var(--color-success)]">当前题已用</span> : <span />}
                  <div className="flex gap-1">
                    <button type="button" className="text-[10px] font-semibold text-[var(--color-accent)] hover:underline" onClick={() => setProcessorAsset(asset)}>切分/清晰化</button>
                    <button type="button" className="text-[10px] font-semibold text-[var(--color-text-muted)] hover:text-[var(--color-accent)]" onClick={() => void copyImage(asset)}>复制</button>
                    <button type="button" className="text-[10px] font-semibold text-[var(--color-text-muted)] hover:text-[var(--color-accent)]" onClick={() => void copyText(ref, `已复制 ${ref}`)}>引用</button>
                  </div>
                </div>
              </div>
            </article>
          );
        })}
      </div>
      {processorAsset && (
        <ImageOptionProcessorDialog
          open
          sourceUrl={/\.(?:wmf|emf)$/i.test(processorAsset.relative_path)
            ? imageThumbnailUrl(processorAsset.relative_path, 1600) || ''
            : fileUrl(processorAsset.relative_path) || ''}
          sourceName={processorAsset.filename || processorAsset.relative_path}
          onClose={() => setProcessorAsset(null)}
          onApply={(result) => processAsset(processorAsset, result)}
        />
      )}
    </div>
  );
}

function BatchPanel({ aiProcessing, cacheMessage, confirmQueue, confirmClean, batchAnalysis, batchMetadata, fastLatexCleanup, exportJSON, clearCache }: {
  aiProcessing: boolean;
  cacheMessage: string | null;
  confirmQueue: () => void;
  confirmClean: () => void;
  batchAnalysis: () => void;
  batchMetadata: () => void;
  fastLatexCleanup: () => void;
  exportJSON: () => void;
  clearCache: () => void;
}) {
  return (
    <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-3">
      <h2 className="text-sm font-bold">批量动作</h2>
      <div className="mt-3 grid gap-2">
        <button onClick={confirmQueue} className={SOFT_BUTTON_CLASS}>确认当前队列</button>
        <button onClick={confirmClean} className={SOFT_BUTTON_CLASS}>确认无风险题</button>
        <button onClick={fastLatexCleanup} disabled={aiProcessing} className={SOFT_BUTTON_CLASS}>快速清洗 LaTeX</button>
        <button onClick={batchAnalysis} disabled={aiProcessing} className={SOFT_BUTTON_CLASS}>批量生成解析</button>
        <button onClick={batchMetadata} disabled={aiProcessing} className={SOFT_BUTTON_CLASS}>AI 补全元数据</button>
        <button onClick={exportJSON} className={SOFT_BUTTON_CLASS}>导出草稿 JSON</button>
        <button onClick={clearCache} className={SOFT_BUTTON_CLASS}>清除本地缓存</button>
      </div>
      {cacheMessage && <p className="mt-3 text-xs text-[var(--color-text-muted)]">{cacheMessage}</p>}
    </div>
  );
}

function SuggestionPanel({ suggestion, accept, dismiss }: { suggestion: Partial<ReviewQuestionDraft>; accept: () => void; dismiss: () => void }) {
  return (
    <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-3">
      <h2 className="text-sm font-bold">AI 建议</h2>
      <pre className="mt-2 max-h-44 overflow-auto whitespace-pre-wrap rounded-md bg-[var(--color-bg-card)] p-2 text-xs">{JSON.stringify(suggestion, null, 2)}</pre>
      <div className="mt-2 flex gap-2">
        <button onClick={accept} className={PRIMARY_BUTTON_CLASS}>应用建议</button>
        <button onClick={dismiss} className={SOFT_BUTTON_CLASS}>忽略</button>
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return <label className="mt-3 block"><div className="mb-1 text-xs font-bold text-[var(--color-text-muted)]">{label}</div>{children}</label>;
}

function Stat({ label, value, tone }: { label: string; value: number; tone?: 'danger' | 'success' }) {
  const color = tone === 'danger' ? 'text-[var(--color-danger)]' : tone === 'success' ? 'text-[var(--color-success)]' : 'text-[var(--color-text-secondary)]';
  return <span className="rounded-full bg-[var(--color-bg-hover)] px-3 py-1 font-semibold"><span>{label}</span> <b className={color}>{value}</b></span>;
}

function CenteredState({ title, desc, action, onAction }: { title: string; desc: string; action?: string; onAction?: () => void }) {
  return (
    <section aria-label={title} className="flex min-h-screen items-center justify-center bg-[var(--color-bg)] p-6">
      <div className="max-w-md text-center">
        <h1 className="text-xl font-bold">{title}</h1>
        <p className="mt-2 text-sm text-[var(--color-text-secondary)]">{desc}</p>
        {action && <button className={`${PRIMARY_BUTTON_CLASS} mt-4`} onClick={onAction}>{action}</button>}
      </div>
    </section>
  );
}

function statusLabel(status: ReviewQuestionDraft['status'] | KnowledgeReviewDraft['status']): string {
  return { pending: '待确认', modified: '已修改', discarded: '已丢弃', confirmed: '已确认' }[status] ?? status;
}
