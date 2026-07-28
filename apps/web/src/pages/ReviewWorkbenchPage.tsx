import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { useNavigate, useParams } from 'react-router-dom';

import ImportStemRenderer from '../components/import/ImportStemRenderer';
import {
  batchGenerateAnalysis,
  completeImportDraftMetadata,
  fetchImportTask,
  generateSingleAnalysis,
  saveReviewedQuestions,
} from '../services/api';
import type {
  Figure,
  FigureReferenceIssue,
  ImportMediaAsset,
  ImportPipelineTaskResponse,
  Option,
  ReviewQuestionDraft,
  SaveReviewedQuestionsResponse,
  SubQuestion,
} from '../types';
import { normalizeShortInlineDisplayMath } from '../utils/mathText';

type QueueKey = 'risk' | 'missing_answer' | 'missing_options' | 'image_issue' | 'ai_failed_page' | 'pending' | 'modified' | 'confirmed' | 'discarded' | 'all';
type RiskKind = 'empty_title' | 'missing_answer' | 'missing_options' | 'missing_knowledge' | 'image_issue';

interface RiskItem {
  kind: RiskKind;
  severity: 'danger' | 'warning';
  message: string;
}

interface PageResult {
  page_no?: number;
  status?: string;
  page_image_path?: string;
  error?: string;
  question_count?: number;
}

interface ReviewTaskMeta {
  warnings: string[];
  pageResults: PageResult[];
  mediaAssets: ImportMediaAsset[];
}

interface CachedReviewState {
  version: 1;
  taskId: string;
  savedAt: string;
  drafts: ReviewQuestionDraft[];
  taskMeta: ReviewTaskMeta;
  currentIndex: number;
  queue: QueueKey;
}

const REVIEW_CACHE_PREFIX = 'physics_vault_review_cache.';
const REVIEW_CACHE_VERSION = 1;

const TYPE_OPTIONS = [
  { value: 'single_choice', label: '单选题' },
  { value: 'multi_choice', label: '多选题' },
  { value: 'fill', label: '填空题' },
  { value: 'experiment', label: '实验题' },
  { value: 'calculation', label: '计算题' },
];

const TYPE_LABELS = Object.fromEntries(TYPE_OPTIONS.map((item) => [item.value, item.label]));
const INPUT_CLASS = 'w-full rounded-md border border-[var(--color-border)] bg-[var(--color-bg-card)] px-3 py-2 text-sm text-[var(--color-text)] outline-none focus:border-[var(--color-accent)]';
const TEXTAREA_CLASS = 'w-full resize-y rounded-md border border-[var(--color-border)] bg-[var(--color-bg-card)] px-3 py-2 text-sm leading-7 text-[var(--color-text)] outline-none focus:border-[var(--color-accent)]';
const SOFT_BUTTON_CLASS = 'rounded-md border border-[var(--color-border)] bg-[var(--color-bg-card)] px-3 py-2 text-sm font-semibold text-[var(--color-text-secondary)] disabled:cursor-not-allowed disabled:opacity-45';
const PRIMARY_BUTTON_CLASS = 'rounded-md bg-[var(--color-accent)] px-3 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-45';

function reviewCacheKey(taskId: string): string {
  return `${REVIEW_CACHE_PREFIX}${taskId}`;
}

function readReviewCache(taskId: string): CachedReviewState | null {
  try {
    const raw = window.localStorage.getItem(reviewCacheKey(taskId));
    if (!raw) return null;
    const parsed = JSON.parse(raw) as CachedReviewState;
    if (parsed.version !== REVIEW_CACHE_VERSION || parsed.taskId !== taskId || !Array.isArray(parsed.drafts)) return null;
    return parsed;
  } catch {
    return null;
  }
}

function writeReviewCache(taskId: string, state: Omit<CachedReviewState, 'version' | 'taskId' | 'savedAt'>): void {
  try {
    window.localStorage.setItem(reviewCacheKey(taskId), JSON.stringify({
      version: REVIEW_CACHE_VERSION,
      taskId,
      savedAt: new Date().toISOString(),
      ...state,
    }));
  } catch {
    // Ignore storage quota or privacy-mode failures; the page still works.
  }
}

function clearReviewCache(taskId: string): void {
  try {
    window.localStorage.removeItem(reviewCacheKey(taskId));
  } catch {
    // Ignore localStorage failures.
  }
}

function fileUrl(path?: string | null): string | null {
  const trimmed = String(path || '').trim();
  if (!trimmed) return null;
  if (trimmed.startsWith('/files/')) return trimmed;
  return `/files/${trimmed.replace(/^\.?\//, '')}`;
}

function computeFigureIssues(title: string, figures: Figure[]): FigureReferenceIssue[] {
  const issues: FigureReferenceIssue[] = [];
  const referenced = new Set<string>();
  const refPattern = /!\[fig:([^\]]+)\]/g;
  let match: RegExpExecArray | null;
  while ((match = refPattern.exec(title)) !== null) referenced.add(match[1]);
  const actual = new Set(figures.map((figure) => figure.fig_uuid));
  for (const figure of figures) {
    if (!referenced.has(figure.fig_uuid)) issues.push({ type: 'unreferenced_figure', message: `图片 ${figure.fig_uuid} 未被题干引用`, figUuid: figure.fig_uuid });
  }
  for (const uuid of referenced) {
    if (!actual.has(uuid)) issues.push({ type: 'missing_figure', message: `题干引用了不存在的图片 ${uuid}`, figUuid: uuid });
  }
  return issues;
}

function normalizeOptions(options: unknown): Option[] {
  if (!Array.isArray(options)) return [];
  return options
    .filter((item): item is Record<string, unknown> => typeof item === 'object' && item !== null)
    .map((item) => ({
      opt: String(item.opt ?? ''),
      content: normalizeShortInlineDisplayMath(String(item.content ?? '')),
    }));
}

function normalizeDraft(raw: Record<string, unknown>, index: number): ReviewQuestionDraft {
  const title = normalizeShortInlineDisplayMath(String(raw.title ?? raw.stem ?? ''));
  const figures = Array.isArray(raw.figures) ? (raw.figures as Figure[]) : [];
  return {
    question_id: String(raw.question_id ?? `draft-${index + 1}`),
    question_type: String(raw.question_type || 'calculation'),
    title,
    options: normalizeOptions(raw.options),
    answer: normalizeShortInlineDisplayMath(String(raw.answer ?? '')),
    analysis: normalizeShortInlineDisplayMath(String(raw.analysis ?? '')),
    sub_questions: Array.isArray(raw.sub_questions) ? (raw.sub_questions as SubQuestion[]) : [],
    figures,
    difficulty: raw.difficulty !== null && raw.difficulty !== undefined ? Number(raw.difficulty) : null,
    knowledge_point: String(raw.knowledge_point ?? ''),
    tags: Array.isArray(raw.tags) ? raw.tags.map(String) : [],
    source: String(raw.source ?? ''),
    import_batch_id: raw.import_batch_id ? String(raw.import_batch_id) : undefined,
    source_page: raw.source_page !== null && raw.source_page !== undefined ? Number(raw.source_page) : null,
    source_region_id: raw.source_region_id ? String(raw.source_region_id) : null,
    raw_text: raw.raw_text ? normalizeShortInlineDisplayMath(String(raw.raw_text)) : null,
    status: 'pending',
    figureIssues: computeFigureIssues(title, figures),
  };
}

function cloneDraft(draft: ReviewQuestionDraft): ReviewQuestionDraft {
  return JSON.parse(JSON.stringify(draft)) as ReviewQuestionDraft;
}

function getRiskItems(draft: ReviewQuestionDraft): RiskItem[] {
  const risks: RiskItem[] = [];
  if (!draft.title.trim()) risks.push({ kind: 'empty_title', severity: 'danger', message: '题干为空' });
  if (!draft.answer.trim()) risks.push({ kind: 'missing_answer', severity: 'warning', message: '缺少答案' });
  if ((draft.question_type === 'single_choice' || draft.question_type === 'multi_choice') && draft.options.length === 0) risks.push({ kind: 'missing_options', severity: 'danger', message: '选择题缺少选项' });
  if (!draft.knowledge_point.trim()) risks.push({ kind: 'missing_knowledge', severity: 'warning', message: '未标知识点' });
  for (const issue of draft.figureIssues) risks.push({ kind: 'image_issue', severity: 'danger', message: issue.message });
  return risks;
}

function applyAiPatch(text: string): Partial<ReviewQuestionDraft> {
  const trimmed = text.trim();
  try {
    if (trimmed.startsWith('{')) {
      const data = JSON.parse(trimmed) as Record<string, unknown>;
      return {
        ...(typeof data.question_type === 'string' ? { question_type: data.question_type } : {}),
        ...(typeof data.difficulty === 'number' ? { difficulty: Math.max(1, Math.min(5, data.difficulty)) } : {}),
        ...(typeof data.knowledge_point === 'string' ? { knowledge_point: data.knowledge_point } : {}),
        ...(Array.isArray(data.tags) ? { tags: data.tags.map(String) } : {}),
        ...(typeof data.source === 'string' ? { source: data.source } : {}),
        ...(typeof data.answer === 'string' ? { answer: normalizeShortInlineDisplayMath(data.answer) } : {}),
        ...(Array.isArray(data.options) ? { options: normalizeOptions(data.options) } : {}),
        ...(typeof data.analysis === 'string' ? { analysis: normalizeShortInlineDisplayMath(data.analysis) } : {}),
        ...(Array.isArray(data.sub_questions) ? { sub_questions: data.sub_questions as SubQuestion[] } : {}),
      };
    }
  } catch {
    // Keep the generated text as analysis if it is not valid JSON.
  }
  return { analysis: normalizeShortInlineDisplayMath(text) };
}

function matchesQueue(draft: ReviewQuestionDraft, queue: QueueKey): boolean {
  if (queue === 'all') return true;
  if (queue === 'pending' || queue === 'modified' || queue === 'confirmed' || queue === 'discarded') return draft.status === queue;
  const risks = getRiskItems(draft);
  if (queue === 'risk') return risks.length > 0;
  if (queue === 'missing_answer') return risks.some((risk) => risk.kind === 'missing_answer');
  if (queue === 'missing_options') return risks.some((risk) => risk.kind === 'missing_options');
  if (queue === 'image_issue') return risks.some((risk) => risk.kind === 'image_issue');
  return false;
}

export default function ReviewWorkbenchPage() {
  const { taskId } = useParams<{ taskId: string }>();
  const navigate = useNavigate();
  const originalsRef = useRef<Map<string, ReviewQuestionDraft>>(new Map());

  const [drafts, setDrafts] = useState<ReviewQuestionDraft[]>([]);
  const [taskMeta, setTaskMeta] = useState<ReviewTaskMeta>({ warnings: [], pageResults: [], mediaAssets: [] });
  const [currentIndex, setCurrentIndex] = useState(0);
  const [queue, setQueue] = useState<QueueKey>('risk');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [aiProcessing, setAiProcessing] = useState(false);
  const [aiMessage, setAiMessage] = useState<string | null>(null);
  const [aiSuggestion, setAiSuggestion] = useState<Partial<ReviewQuestionDraft> | null>(null);
  const [copyMessage, setCopyMessage] = useState<string | null>(null);
  const [cacheMessage, setCacheMessage] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saveResult, setSaveResult] = useState<SaveReviewedQuestionsResponse | null>(null);

  useEffect(() => {
    if (!taskId) return;
    setLoading(true);
    setError(null);
    fetchImportTask(taskId)
      .then((task: ImportPipelineTaskResponse) => {
        const result = task.result ?? {};
        const questions = Array.isArray(result.questions) ? result.questions as Record<string, unknown>[] : [];
        const parsed = questions.map((raw, index) => normalizeDraft(raw, index));
        const meta = {
          warnings: Array.isArray(result.warnings) ? result.warnings.map(String) : [],
          pageResults: Array.isArray(result.page_results) ? result.page_results as PageResult[] : [],
          mediaAssets: Array.isArray(result.media_assets) ? result.media_assets as ImportMediaAsset[] : [],
        };
        const cached = readReviewCache(taskId);
        originalsRef.current = new Map(parsed.map((draft) => [draft.question_id, cloneDraft(draft)]));
        if (cached?.drafts.length) {
          const restored = cached.drafts.map((draft, index) => normalizeDraft(draft as unknown as Record<string, unknown>, index));
          setDrafts(restored);
          setTaskMeta(cached.taskMeta ?? meta);
          setCurrentIndex(Math.min(cached.currentIndex ?? 0, Math.max(restored.length - 1, 0)));
          setQueue(cached.queue ?? 'risk');
          setCacheMessage(`已恢复 ${new Date(cached.savedAt).toLocaleString()} 的本地校对缓存`);
        } else {
          setDrafts(parsed);
          setTaskMeta(meta);
          setCurrentIndex(0);
          setCacheMessage(null);
        }
      })
      .catch((err: unknown) => setError(err instanceof Error ? err.message : '加载校对任务失败'))
      .finally(() => setLoading(false));
  }, [taskId]);

  const currentDraft = drafts[currentIndex] ?? null;
  const currentPage = useMemo(() => {
    if (!currentDraft?.source_page) return null;
    return taskMeta.pageResults.find((page) => page.page_no === currentDraft.source_page) ?? null;
  }, [currentDraft, taskMeta.pageResults]);
  const failedPages = useMemo(() => taskMeta.pageResults.filter((page) => page.status === 'failed'), [taskMeta.pageResults]);

  const counts = useMemo(() => ({
    total: drafts.length,
    risk: drafts.filter((draft) => getRiskItems(draft).length > 0).length,
    missingAnswer: drafts.filter((draft) => getRiskItems(draft).some((risk) => risk.kind === 'missing_answer')).length,
    missingOptions: drafts.filter((draft) => getRiskItems(draft).some((risk) => risk.kind === 'missing_options')).length,
    imageIssue: drafts.filter((draft) => getRiskItems(draft).some((risk) => risk.kind === 'image_issue')).length,
    failedPage: failedPages.length,
    pending: drafts.filter((draft) => draft.status === 'pending').length,
    modified: drafts.filter((draft) => draft.status === 'modified').length,
    confirmed: drafts.filter((draft) => draft.status === 'confirmed').length,
    discarded: drafts.filter((draft) => draft.status === 'discarded').length,
  }), [drafts, failedPages.length]);

  const filteredDrafts = useMemo(() => drafts.map((draft, index) => ({ draft, index })).filter(({ draft }) => matchesQueue(draft, queue)), [drafts, queue]);

  useEffect(() => {
    if (!taskId || loading || drafts.length === 0) return;
    const timer = window.setTimeout(() => {
      writeReviewCache(taskId, { drafts, taskMeta, currentIndex, queue });
      setCacheMessage('本地校对缓存已自动保存');
    }, 500);
    return () => window.clearTimeout(timer);
  }, [currentIndex, drafts, loading, queue, taskId, taskMeta]);

  const updateDraftAt = useCallback((index: number, patch: Partial<ReviewQuestionDraft>) => {
    setDrafts((prev) => {
      const next = [...prev];
      const updated = { ...next[index], ...patch };
      updated.title = normalizeShortInlineDisplayMath(updated.title);
      updated.answer = normalizeShortInlineDisplayMath(updated.answer);
      updated.analysis = normalizeShortInlineDisplayMath(updated.analysis);
      updated.options = normalizeOptions(updated.options);
      updated.figureIssues = computeFigureIssues(updated.title, updated.figures);
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

  const goNext = useCallback(() => setCurrentIndex((prev) => Math.min(drafts.length - 1, prev + 1)), [drafts.length]);
  const goNextRisk = useCallback(() => {
    const next = drafts.findIndex((draft, index) => index > currentIndex && draft.status !== 'discarded' && getRiskItems(draft).length > 0);
    if (next >= 0) return setCurrentIndex(next);
    const first = drafts.findIndex((draft) => draft.status !== 'discarded' && getRiskItems(draft).length > 0);
    if (first >= 0) setCurrentIndex(first);
  }, [currentIndex, drafts]);

  const confirmAndNext = useCallback(() => {
    updateStatus('confirmed');
    const nextRisk = drafts.findIndex((draft, index) => index > currentIndex && draft.status !== 'discarded' && getRiskItems(draft).length > 0);
    if (nextRisk >= 0) setCurrentIndex(nextRisk);
    else goNext();
  }, [currentIndex, drafts, goNext, updateStatus]);

  const restoreCurrent = useCallback(() => {
    if (!currentDraft) return;
    const original = originalsRef.current.get(currentDraft.question_id);
    if (original) updateDraftAt(currentIndex, cloneDraft(original));
  }, [currentDraft, currentIndex, updateDraftAt]);

  const copyText = useCallback(async (text: string, message: string) => {
    await navigator.clipboard.writeText(text);
    setCopyMessage(message);
    window.setTimeout(() => setCopyMessage(null), 1800);
  }, []);

  const copyImage = useCallback(async (asset: ImportMediaAsset) => {
    const imageUrl = fileUrl(asset.relative_path);
    if (!imageUrl || !navigator.clipboard || typeof ClipboardItem === 'undefined') {
      setCopyMessage('当前浏览器不支持直接复制图片');
      window.setTimeout(() => setCopyMessage(null), 1800);
      return;
    }
    try {
      const response = await fetch(imageUrl);
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
    const uuid = asset.image_id || asset.filename || asset.relative_path;
    const reference = `![fig:${uuid}]`;
    const figures = currentDraft.figures.some((figure) => figure.fig_uuid === uuid)
      ? currentDraft.figures
      : [...currentDraft.figures, { fig_uuid: uuid, local_path: asset.relative_path }];
    const title = currentDraft.title.includes(reference) ? currentDraft.title : `${currentDraft.title.trimEnd()}\n${reference}`.trimStart();
    updateDraftAt(currentIndex, { figures, title });
    setCopyMessage(`已插入 ${reference}`);
    window.setTimeout(() => setCopyMessage(null), 1800);
  }, [currentDraft, currentIndex, updateDraftAt]);

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
        clearReviewCache(taskId);
        setCacheMessage('已保存入库，本地校对缓存已清除');
      }
    } catch (err) {
      setSaveError(`保存失败：${err instanceof Error ? err.message : '未知错误'}`);
    } finally {
      setSaving(false);
    }
  }, [drafts, taskId]);

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.target instanceof HTMLInputElement || event.target instanceof HTMLTextAreaElement || event.target instanceof HTMLSelectElement) return;
      if (event.key === 'Enter') confirmAndNext();
      if (event.key.toLowerCase() === 'r') goNextRisk();
      if (event.key === 'ArrowDown') goNext();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [confirmAndNext, goNext, goNextRisk]);

  if (!taskId) return <CenteredState title="校对中心" desc="请先在“导入识别”中完成一个导入任务，再从任务结果进入校对。" action="去导入识别" onAction={() => navigate('/import')} />;
  if (loading) return <CenteredState title="正在加载校对任务" desc="正在读取导入结果和图片缓存。" />;
  if (error) return <CenteredState title={error} desc={`任务 ID：${taskId}`} action="返回导入识别" onAction={() => navigate('/import')} />;
  if (drafts.length === 0) return <CenteredState title="暂无可校对数据" desc="该任务没有解析出题目，请先完成导入识别。" action="返回导入识别" onAction={() => navigate('/import')} />;

  const risks = currentDraft ? getRiskItems(currentDraft) : [];

  return (
    <main className="min-h-screen bg-[var(--color-bg)] text-[var(--color-text)]">
      <header className="sticky top-0 z-20 border-b border-[var(--color-border)] bg-[var(--color-bg-card)]/95 px-6 py-3 backdrop-blur">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <button className={SOFT_BUTTON_CLASS} onClick={() => navigate('/import')}>返回导入</button>
            <div>
              <h1 className="text-lg font-bold">校对中心</h1>
              <p className="text-xs text-[var(--color-text-muted)]">编辑、预览、图片缓存和原文对照在同一个工作台内完成。</p>
            </div>
          </div>
          <div className="flex flex-wrap gap-2 text-xs">
            <Stat label="总题数" value={counts.total} />
            <Stat label="高风险" value={counts.risk} tone="danger" />
            <Stat label="失败页" value={counts.failedPage} />
            <Stat label="已确认" value={counts.confirmed} tone="success" />
          </div>
        </div>
      </header>

      <section className="grid h-[calc(100vh-73px)] grid-cols-[360px_minmax(760px,1fr)_300px] overflow-hidden">
        <aside className="border-r border-[var(--color-border)] bg-[var(--color-bg-card)] p-4">
          <QueueTabs queue={queue} setQueue={setQueue} counts={counts} />
          <div className="mt-4 h-[calc(100vh-250px)] space-y-2 overflow-y-auto pr-1">
            {filteredDrafts.map(({ draft, index }) => (
              <button
                key={draft.question_id}
                onClick={() => setCurrentIndex(index)}
                className={`w-full rounded-lg border p-3 text-left ${index === currentIndex ? 'border-[var(--color-accent)] bg-[#eef5ff]' : 'border-[var(--color-border)] bg-[var(--color-bg)]'}`}
              >
                <div className="flex items-center justify-between gap-2 text-sm">
                  <span className="font-bold text-[var(--color-accent)]">{index + 1}</span>
                  <span className="rounded-full bg-[var(--color-bg-hover)] px-2 py-0.5 text-xs">{TYPE_LABELS[draft.question_type] ?? draft.question_type}</span>
                  {draft.figures.length > 0 && <span className="text-xs text-[var(--color-text-muted)]">图 {draft.figures.length}</span>}
                  <span className="ml-auto text-xs text-[var(--color-text-muted)]">{statusLabel(draft.status)}</span>
                </div>
                <div className="mt-2 line-clamp-2 text-xs leading-5 text-[var(--color-text-secondary)]">{draft.title || '无题干'}</div>
                {getRiskItems(draft).slice(0, 2).map((risk) => <div key={risk.kind} className="mt-1 text-xs font-semibold text-[var(--color-danger)]">{risk.message}</div>)}
              </button>
            ))}
          </div>
        </aside>

        <section className="overflow-y-auto p-6">
          {risks.length > 0 && (
            <div className="mb-4 rounded-lg border border-[var(--color-danger)] bg-[#fff0f0] p-4 text-sm text-[var(--color-danger)]">
              <div className="font-bold">需要优先检查</div>
              <div>{risks.map((risk) => risk.message).join('、')}</div>
            </div>
          )}
          {currentDraft && (
            <div className="grid grid-cols-2 gap-5">
              <EditorPanel draft={currentDraft} updateField={updateCurrentField} updateDraftAt={(patch) => updateDraftAt(currentIndex, patch)} />
              <LivePreviewPanel draft={currentDraft} />
            </div>
          )}
        </section>

        <aside className="space-y-4 overflow-y-auto border-l border-[var(--color-border)] bg-[var(--color-bg-card)] p-4">
          <OriginalPreviewPanel draft={currentDraft} page={currentPage} warnings={taskMeta.warnings} />
          <ImageCachePanel assets={taskMeta.mediaAssets} draft={currentDraft} copyText={copyText} copyImage={copyImage} attachAsset={attachAssetToCurrent} copyMessage={copyMessage} />
          <ActionPanel
            aiProcessing={aiProcessing}
            confirmAndNext={confirmAndNext}
            goNextRisk={goNextRisk}
            discard={() => updateStatus('discarded')}
            restore={restoreCurrent}
            generateSuggestion={handleSingleAiSuggestion}
          />
          {aiMessage && <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-3 text-xs text-[var(--color-text-secondary)]">{aiMessage}</div>}
          {aiSuggestion && <SuggestionPanel suggestion={aiSuggestion} accept={acceptSuggestion} dismiss={() => setAiSuggestion(null)} />}
          <BatchPanel
            aiProcessing={aiProcessing}
            cacheMessage={cacheMessage}
            confirmQueue={() => {
              const indexes = new Set(filteredDrafts.map((item) => item.index));
              setDrafts((prev) => prev.map((draft, index) => indexes.has(index) && draft.status !== 'discarded' ? { ...draft, status: 'confirmed' } : draft));
            }}
            confirmClean={() => setDrafts((prev) => prev.map((draft) => draft.status !== 'discarded' && getRiskItems(draft).length === 0 ? { ...draft, status: 'confirmed' } : draft))}
            batchAnalysis={handleBatchAnalysis}
            batchMetadata={handleBatchMetadata}
            exportJSON={handleExportJSON}
            clearCache={() => {
              if (!taskId) return;
              clearReviewCache(taskId);
              setCacheMessage('本地校对缓存已清除');
            }}
            save={handleSave}
            saving={saving}
            canSave={counts.confirmed > 0}
          />
          {(saveError || saveResult) && (
            <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-3 text-xs">
              {saveError && <p className="text-[var(--color-danger)]">{saveError}</p>}
              {saveResult && <p className="text-[var(--color-success)]">已入库 {saveResult.saved_count} 题，跳过 {saveResult.skipped_count} 题，失败 {saveResult.failed_count} 题。</p>}
            </div>
          )}
        </aside>
      </section>
    </main>
  );
}

function QueueTabs({ queue, setQueue, counts }: { queue: QueueKey; setQueue: (queue: QueueKey) => void; counts: Record<string, number> }) {
  const tabs: [QueueKey, string][] = [
    ['risk', `全部风险 ${counts.risk}`],
    ['missing_answer', `缺答案 ${counts.missingAnswer}`],
    ['missing_options', `缺选项 ${counts.missingOptions}`],
    ['image_issue', `图片异常 ${counts.imageIssue}`],
    ['ai_failed_page', `AI失败页 ${counts.failedPage}`],
    ['pending', `待确认 ${counts.pending}`],
    ['modified', `已修改 ${counts.modified}`],
    ['confirmed', `已确认 ${counts.confirmed}`],
    ['discarded', `已丢弃 ${counts.discarded}`],
    ['all', `全部 ${counts.total}`],
  ];
  return (
    <div className="grid grid-cols-2 gap-2">
      {tabs.map(([key, label]) => (
        <button key={key} onClick={() => setQueue(key)} className={`rounded-md border px-3 py-2 text-sm ${queue === key ? 'border-[var(--color-accent)] bg-[#eef5ff] text-[var(--color-accent)]' : 'border-[var(--color-border)] bg-[var(--color-bg)] text-[var(--color-text-secondary)]'}`}>
          {label}
        </button>
      ))}
    </div>
  );
}

function EditorPanel({ draft, updateField, updateDraftAt }: {
  draft: ReviewQuestionDraft;
  updateField: (field: keyof ReviewQuestionDraft, value: unknown) => void;
  updateDraftAt: (patch: Partial<ReviewQuestionDraft>) => void;
}) {
  const updateOption = (index: number, content: string) => {
    const next = [...draft.options];
    next[index] = { ...next[index], content };
    updateField('options', next);
  };
  return (
    <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-card)] p-4">
      <h2 className="mb-3 text-sm font-bold">编辑区</h2>
      <div className="grid grid-cols-3 gap-3">
        <Field label="题型">
          <select className={INPUT_CLASS} value={draft.question_type} onChange={(event) => updateField('question_type', event.target.value)}>
            {TYPE_OPTIONS.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
          </select>
        </Field>
        <Field label="难度">
          <input className={INPUT_CLASS} value={draft.difficulty ?? ''} onChange={(event) => updateField('difficulty', event.target.value ? Number(event.target.value) : null)} />
        </Field>
        <Field label="来源">
          <input className={INPUT_CLASS} value={draft.source} onChange={(event) => updateField('source', event.target.value)} />
        </Field>
      </div>
      <Field label="知识点">
        <input className={INPUT_CLASS} value={draft.knowledge_point} onChange={(event) => updateField('knowledge_point', event.target.value)} />
      </Field>
      <Field label="标签">
        <input className={INPUT_CLASS} value={draft.tags.join('、')} onChange={(event) => updateField('tags', event.target.value.split(/[、,，]/).map((item) => item.trim()).filter(Boolean))} />
      </Field>
      <Field label="题干">
        <textarea className={TEXTAREA_CLASS} rows={8} value={draft.title} onChange={(event) => updateField('title', event.target.value)} />
      </Field>
      <div className="space-y-2">
        <div className="text-xs font-bold text-[var(--color-text-muted)]">选项</div>
        {draft.options.map((option, index) => (
          <div key={`${option.opt}-${index}`} className="grid grid-cols-[32px_1fr_auto] items-center gap-2">
            <span className="font-bold text-[var(--color-accent)]">{option.opt || String.fromCharCode(65 + index)}</span>
            <input className={INPUT_CLASS} value={option.content} onChange={(event) => updateOption(index, event.target.value)} />
            <button className={SOFT_BUTTON_CLASS} onClick={() => updateField('options', draft.options.filter((_, i) => i !== index))}>删除</button>
          </div>
        ))}
        <button className={SOFT_BUTTON_CLASS} onClick={() => updateField('options', [...draft.options, { opt: String.fromCharCode(65 + draft.options.length), content: '' }])}>添加选项</button>
      </div>
      <Field label="答案">
        <textarea className={TEXTAREA_CLASS} rows={4} value={draft.answer} onChange={(event) => updateField('answer', event.target.value)} />
      </Field>
      <Field label="解析">
        <textarea className={TEXTAREA_CLASS} rows={7} value={draft.analysis} onChange={(event) => updateField('analysis', event.target.value)} />
      </Field>
      <div className="mt-3 flex gap-2">
        <button className={SOFT_BUTTON_CLASS} onClick={() => updateDraftAt({ answer: '', analysis: '' })}>清空答案解析</button>
      </div>
    </div>
  );
}

function LivePreviewPanel({ draft }: { draft: ReviewQuestionDraft }) {
  return (
    <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-card)] p-4">
      <h2 className="mb-3 text-sm font-bold">实时预览区</h2>
      <PreviewSection title="题干"><ImportStemRenderer title={draft.title || '（无题干）'} figures={draft.figures} /></PreviewSection>
      {draft.options.length > 0 && (
        <PreviewSection title="选项">
          <div className="space-y-2">{draft.options.map((option) => <div key={option.opt} className="flex gap-2"><b className="text-[var(--color-accent)]">{option.opt}.</b><ImportStemRenderer title={option.content} figures={draft.figures} maxImageHeight={80} /></div>)}</div>
        </PreviewSection>
      )}
      <PreviewSection title="答案"><ImportStemRenderer title={draft.answer || '（暂无）'} figures={draft.figures} maxImageHeight={80} /></PreviewSection>
      <PreviewSection title="解析"><ImportStemRenderer title={draft.analysis || '（暂无）'} figures={draft.figures} maxImageHeight={80} /></PreviewSection>
    </div>
  );
}

function OriginalPreviewPanel({ draft, page, warnings }: { draft: ReviewQuestionDraft | null; page: PageResult | null; warnings: string[] }) {
  const image = fileUrl(page?.page_image_path);
  return (
    <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-3">
      <h2 className="text-sm font-bold">原文对照</h2>
      {warnings.length > 0 && <div className="mt-2 text-xs text-[var(--color-danger)]">{warnings.slice(0, 2).join('；')}</div>}
      {image ? <img src={image} className="mt-3 max-h-64 w-full object-contain" /> : <div className="mt-3 rounded-md border border-dashed border-[var(--color-border)] p-3 text-xs text-[var(--color-text-muted)]">{draft?.raw_text || '当前题没有可定位的页图。'}</div>}
    </div>
  );
}

function ImageCachePanel({ assets, draft, copyText, copyImage, attachAsset, copyMessage }: {
  assets: ImportMediaAsset[];
  draft: ReviewQuestionDraft | null;
  copyText: (text: string, message: string) => Promise<void>;
  copyImage: (asset: ImportMediaAsset) => Promise<void>;
  attachAsset: (asset: ImportMediaAsset) => void;
  copyMessage: string | null;
}) {
  const used = new Set(draft?.figures.map((figure) => figure.local_path) ?? []);
  return (
    <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-3">
      <div className="flex items-center justify-between"><h2 className="text-sm font-bold">图片缓存区</h2>{copyMessage && <span className="text-xs text-[var(--color-success)]">{copyMessage}</span>}</div>
      {assets.length === 0 && <div className="mt-3 rounded-md border border-dashed border-[var(--color-border)] p-3 text-xs text-[var(--color-text-muted)]">暂无缓存图片。导入识别提取到图片后会显示在这里。</div>}
      <div className="mt-3 space-y-3">
        {assets.map((asset) => {
          const ref = `![fig:${asset.image_id || asset.filename || asset.relative_path}]`;
          return (
            <div key={asset.relative_path} className="rounded-md border border-[var(--color-border)] p-2">
              <img src={fileUrl(asset.relative_path) ?? ''} className="max-h-28 w-full object-contain" />
              <div className="mt-1 truncate text-[11px] text-[var(--color-text-muted)]">{asset.filename}</div>
              {used.has(asset.relative_path) && <div className="mt-1 text-[11px] font-semibold text-[var(--color-success)]">当前题已用</div>}
              <div className="mt-2 flex flex-wrap gap-1">
                <button className={SOFT_BUTTON_CLASS} onClick={() => attachAsset(asset)}>插入引用</button>
                <button className={SOFT_BUTTON_CLASS} onClick={() => void copyImage(asset)}>复制图片</button>
                <button className={SOFT_BUTTON_CLASS} onClick={() => void copyText(ref, `已复制 ${ref}`)}>复制引用</button>
                <button className={SOFT_BUTTON_CLASS} onClick={() => void copyText(asset.relative_path, '已复制图片路径')}>复制路径</button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function ActionPanel({ aiProcessing, confirmAndNext, goNextRisk, discard, restore, generateSuggestion }: {
  aiProcessing: boolean;
  confirmAndNext: () => void;
  goNextRisk: () => void;
  discard: () => void;
  restore: () => void;
  generateSuggestion: () => void;
}) {
  return (
    <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-3">
      <h2 className="text-sm font-bold">当前题操作</h2>
      <div className="mt-3 grid gap-2">
        <button onClick={confirmAndNext} className={PRIMARY_BUTTON_CLASS}>确认并下一题</button>
        <button onClick={goNextRisk} className={SOFT_BUTTON_CLASS}>跳到下一个风险题</button>
        <button onClick={discard} className={`${SOFT_BUTTON_CLASS} text-[var(--color-danger)]`}>丢弃此题</button>
        <button onClick={restore} className={SOFT_BUTTON_CLASS}>恢复原稿</button>
        <button onClick={generateSuggestion} disabled={aiProcessing} className={SOFT_BUTTON_CLASS}>生成 AI 修复建议</button>
      </div>
    </div>
  );
}

function BatchPanel({ aiProcessing, cacheMessage, confirmQueue, confirmClean, batchAnalysis, batchMetadata, exportJSON, clearCache, save, saving, canSave }: {
  aiProcessing: boolean;
  cacheMessage: string | null;
  confirmQueue: () => void;
  confirmClean: () => void;
  batchAnalysis: () => void;
  batchMetadata: () => void;
  exportJSON: () => void;
  clearCache: () => void;
  save: () => void;
  saving: boolean;
  canSave: boolean;
}) {
  return (
    <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] p-3">
      <h2 className="text-sm font-bold">批量动作</h2>
      <div className="mt-3 grid gap-2">
        <button onClick={confirmQueue} className={SOFT_BUTTON_CLASS}>确认当前队列</button>
        <button onClick={confirmClean} className={SOFT_BUTTON_CLASS}>确认无风险题</button>
        <button onClick={batchAnalysis} disabled={aiProcessing} className={SOFT_BUTTON_CLASS}>批量生成解析</button>
        <button onClick={batchMetadata} disabled={aiProcessing} className={SOFT_BUTTON_CLASS}>AI 补全元数据</button>
        <button onClick={exportJSON} className={SOFT_BUTTON_CLASS}>导出草稿 JSON</button>
        <button onClick={clearCache} className={SOFT_BUTTON_CLASS}>清除本地缓存</button>
        <button onClick={save} disabled={saving || !canSave} className={PRIMARY_BUTTON_CLASS}>{saving ? '保存中...' : '保存入库'}</button>
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

function PreviewSection({ title, children }: { title: string; children: ReactNode }) {
  return <section className="mb-4"><div className="mb-1 text-xs font-bold text-[var(--color-text-muted)]">{title}</div><div className="rounded-md bg-[var(--color-bg)] p-3 text-sm leading-7">{children}</div></section>;
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
    <main className="flex min-h-screen items-center justify-center bg-[var(--color-bg)] p-6">
      <div className="max-w-md text-center">
        <h1 className="text-xl font-bold">{title}</h1>
        <p className="mt-2 text-sm text-[var(--color-text-secondary)]">{desc}</p>
        {action && <button className={`${PRIMARY_BUTTON_CLASS} mt-4`} onClick={onAction}>{action}</button>}
      </div>
    </main>
  );
}

function statusLabel(status: ReviewQuestionDraft['status']): string {
  return { pending: '待确认', modified: '已修改', discarded: '已丢弃', confirmed: '已确认' }[status] ?? status;
}
