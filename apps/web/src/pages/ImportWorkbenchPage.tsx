import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState, type SetStateAction } from 'react';
import { useNavigate } from 'react-router-dom';

import { analyzeQuestionQuality, findDuplicateQuestionIds, type QuestionQualityCode } from '../services/questionQuality';
import { normalizeShortInlineDisplayMath } from '../utils/mathText';
import {
  confirmImportBatch,
  createImportBatch,
  extractBatchImages,
  fetchImportBatchOverview,
  runImportBatchRecognize,
  type PersistedImportBatchSummary,
} from '../services/importApi';
import type { Figure, ImportMediaAsset, Option, QuestionType } from '../types';

const DocumentPreviewModal = lazy(() => import('../components/import/DocumentPreviewModal'));
const StructuredTextEditor = lazy(() => import('../components/editor/StructuredTextEditor'));

type ImportStrategy = 'auto' | 'document' | 'vision' | 'extract_images';
type JobStatus = 'queued' | 'running' | 'ready' | 'failed';
type JobStep = 'upload' | 'preprocess' | 'recognize' | 'risk_check' | 'review';

interface RawQuestion {
  question_id?: string;
  question_no?: number;
  question_type?: string;
  title?: string;
  options?: Option[];
  answer?: string;
  analysis?: string;
  figures?: { fig_uuid: string; local_path: string }[];
  _ai_refined?: boolean;
}

interface EditableQuestion {
  question_id: string;
  question_no?: number;
  question_type: QuestionType;
  title: string;
  options: Option[];
  answer: string;
  analysis: string;
  figures: Figure[];
  _key: string;
  _aiRefined?: boolean;
}

interface ImportJob {
  id: string;
  file: File;
  fileName: string;
  status: JobStatus;
  step: JobStep;
  batchId?: string;
  contentVersion?: number;
  questionCount: number;
  imageCount: number;
  questions: EditableQuestion[];
  mediaAssets: ImportMediaAsset[];
  notes: string[];
  reviewTaskId?: string;
  error?: string;
  startedAt?: number;
  finishedAt?: number;
}

const ACCEPTED_EXTS = ['.docx', '.doc', '.pdf', '.jpg', '.jpeg', '.png', '.webp', '.md', '.markdown', '.txt'];
const WORD_EXTS = new Set(['.docx', '.doc', '.md', '.markdown', '.txt']);
const VISION_EXTS = new Set(['.pdf', '.jpg', '.jpeg', '.png', '.webp']);
const IMPORT_CONCURRENCY = 2;

const STEPS: { key: JobStep; label: string; desc: string }[] = [
  { key: 'upload', label: '上传', desc: '保存原始材料，生成独立导入批次。' },
  { key: 'preprocess', label: '预处理', desc: '转 Markdown、拆页、渲染或提取图片。' },
  { key: 'recognize', label: '识别', desc: 'OCR / AI 结构化生成题目草稿。' },
  { key: 'risk_check', label: '质检', desc: '检查空题干、缺选项、缺答案等风险。' },
  { key: 'review', label: '待校对', desc: '进入人工校对与入库流程。' },
];

const STRATEGIES: { value: ImportStrategy; title: string; desc: string }[] = [
  { value: 'auto', title: '自动分流', desc: '推荐。按文件类型自动选择文档解析或 OCR。' },
  { value: 'document', title: '文档解析', desc: '适合 Word、Markdown、纯文本，优先保留公式和图片引用。' },
  { value: 'vision', title: 'OCR 识别', desc: '适合 PDF、截图、扫描件，按页面或图片识别。' },
  { value: 'extract_images', title: '仅提取图片', desc: '只整理素材，不调用模型，不生成题目草稿。' },
];

function PreviewLoading() {
  return <div className="fixed inset-0 z-50 grid place-items-center bg-slate-950/40 text-sm text-white">正在加载文档预览…</div>;
}

function EditorLoading() {
  return <div className="min-h-44 rounded-md border border-dashed border-[var(--color-border)] bg-[var(--color-bg-hover)] p-4 text-sm text-[var(--color-text-muted)]">正在加载富文本编辑器…</div>;
}

function makeJobId(): string {
  return `import-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

function makeQuestionKey(): string {
  return `eq-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

function getExtension(name: string): string {
  const dot = name.lastIndexOf('.');
  return dot < 0 ? '' : name.slice(dot).toLowerCase();
}

function formatSize(size: number): string {
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / 1024 / 1024).toFixed(1)} MB`;
}

function formatDuration(startedAt?: number, finishedAt?: number): string {
  if (!startedAt) return '未开始';
  const seconds = Math.max(1, Math.round(((finishedAt ?? Date.now()) - startedAt) / 1000));
  if (seconds < 60) return `${seconds} 秒`;
  const minutes = Math.floor(seconds / 60);
  return `${minutes} 分 ${seconds % 60} 秒`;
}

function toEditable(raw: RawQuestion): EditableQuestion {
  return {
    question_id: raw.question_id ?? '',
    question_no: raw.question_no,
    question_type: (raw.question_type ?? 'calculation') as QuestionType,
    title: normalizeShortInlineDisplayMath(raw.title ?? ''),
    options: Array.isArray(raw.options) ? normalizeOptionsMath(raw.options) : [],
    answer: normalizeShortInlineDisplayMath(raw.answer ?? ''),
    analysis: normalizeShortInlineDisplayMath(raw.analysis ?? ''),
    figures: Array.isArray(raw.figures) ? raw.figures : [],
    _key: makeQuestionKey(),
    _aiRefined: raw._ai_refined,
  };
}

function normalizeOptionsMath(options: Option[]): Option[] {
  return options.map((option) => ({
    ...option,
    content: normalizeShortInlineDisplayMath(String(option.content ?? '')),
  }));
}

function detectRisks(questions: EditableQuestion[]): string[] {
  const duplicateIds = findDuplicateQuestionIds(questions, (question) => question._key);
  const affected = new Map<QuestionQualityCode, Set<string>>();
  questions.forEach((question) => {
    analyzeQuestionQuality(question, { questionId: question._key, duplicateIds }).forEach((issue) => {
      const ids = affected.get(issue.code) ?? new Set<string>();
      ids.add(question._key);
      affected.set(issue.code, ids);
    });
  });
  const count = (code: QuestionQualityCode) => affected.get(code)?.size ?? 0;
  return [
    count('empty_title') ? `${count('empty_title')} 道题题干为空` : '',
    count('missing_options') ? `${count('missing_options')} 道选择题缺少选项` : '',
    count('missing_answer') ? `${count('missing_answer')} 道题缺少答案` : '',
    count('image_issue') ? `${count('image_issue')} 道题图片引用异常` : '',
    count('duplicate_question') ? `${count('duplicate_question')} 道题疑似重复` : '',
    count('duplicate_options') ? `${count('duplicate_options')} 道题存在重复选项` : '',
    count('answer_option_mismatch') ? `${count('answer_option_mismatch')} 道题答案与选项不一致` : '',
    count('latex_delimiter') ? `${count('latex_delimiter')} 道题 LaTeX 分隔符未闭合` : '',
    count('ocr_artifact') ? `${count('ocr_artifact')} 道题含异常 OCR 字符` : '',
  ].filter(Boolean);
}

function guessPipeline(fileName: string): 'document' | 'vision' | 'unknown' {
  const ext = getExtension(fileName);
  if (WORD_EXTS.has(ext)) return 'document';
  if (VISION_EXTS.has(ext)) return 'vision';
  return 'unknown';
}

async function runWithConcurrency<T>(items: T[], limit: number, worker: (item: T) => Promise<void>) {
  const queue = [...items];
  const workers = Array.from({ length: Math.min(limit, queue.length) }, async () => {
    while (queue.length > 0) {
      const item = queue.shift();
      if (item) await worker(item);
    }
  });
  await Promise.all(workers);
}

interface ImportWorkspaceState {
  files: File[];
  directText: string;
  strategy: ImportStrategy;
  jobs: ImportJob[];
  importMessage: string | null;
}

const initialImportWorkspaceState: ImportWorkspaceState = {
  files: [],
  directText: '',
  strategy: 'auto',
  jobs: [],
  importMessage: null,
};

let importWorkspaceState = initialImportWorkspaceState;
const importWorkspaceListeners = new Set<() => void>();

function getImportWorkspaceState(): ImportWorkspaceState {
  return importWorkspaceState;
}

function setImportWorkspaceState(
  updater: SetStateAction<ImportWorkspaceState>,
): void {
  importWorkspaceState =
    typeof updater === 'function'
      ? (updater as (prev: ImportWorkspaceState) => ImportWorkspaceState)(importWorkspaceState)
      : updater;
  importWorkspaceListeners.forEach((listener) => listener());
}

function subscribeImportWorkspace(listener: () => void): () => void {
  importWorkspaceListeners.add(listener);
  return () => importWorkspaceListeners.delete(listener);
}

export default function ImportWorkbenchPage() {
  const navigate = useNavigate();
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const [workspace, setWorkspace] = useState(getImportWorkspaceState);
  const [dragOver, setDragOver] = useState(false);
  const [submittingJobId, setSubmittingJobId] = useState<string | null>(null);
  const [persistedBatches, setPersistedBatches] = useState<PersistedImportBatchSummary[]>([]);
  const [previewFile, setPreviewFile] = useState<File | null>(null);
  const [richTextEditorOpen, setRichTextEditorOpen] = useState(false);

  useEffect(
    () => subscribeImportWorkspace(() => setWorkspace(getImportWorkspaceState())),
    [],
  );

  useEffect(() => {
    void fetchImportBatchOverview(8).then(setPersistedBatches).catch(() => setPersistedBatches([]));
  }, []);

  const setFiles = useCallback((updater: SetStateAction<File[]>) => {
    setImportWorkspaceState((prev) => ({
      ...prev,
      files: typeof updater === 'function' ? (updater as (value: File[]) => File[])(prev.files) : updater,
    }));
  }, []);

  const setDirectText = useCallback((updater: SetStateAction<string>) => {
    setImportWorkspaceState((prev) => ({
      ...prev,
      directText:
        typeof updater === 'function' ? (updater as (value: string) => string)(prev.directText) : updater,
    }));
  }, []);

  const setStrategy = useCallback((updater: SetStateAction<ImportStrategy>) => {
    setImportWorkspaceState((prev) => ({
      ...prev,
      strategy:
        typeof updater === 'function' ? (updater as (value: ImportStrategy) => ImportStrategy)(prev.strategy) : updater,
    }));
  }, []);

  const setJobs = useCallback((updater: SetStateAction<ImportJob[]>) => {
    setImportWorkspaceState((prev) => ({
      ...prev,
      jobs: typeof updater === 'function' ? (updater as (value: ImportJob[]) => ImportJob[])(prev.jobs) : updater,
    }));
  }, []);

  const setImportMessage = useCallback((updater: SetStateAction<string | null>) => {
    setImportWorkspaceState((prev) => ({
      ...prev,
      importMessage:
        typeof updater === 'function'
          ? (updater as (value: string | null) => string | null)(prev.importMessage)
          : updater,
    }));
  }, []);

  const {
    files,
    directText,
    strategy,
    jobs,
    importMessage,
  } = workspace;
  const hasRunningJobs = jobs.some((job) => job.status === 'running' || job.status === 'queued');
  const canStart = !hasRunningJobs && (files.length > 0 || directText.trim().length > 0);

  const queuedSummary = useMemo(() => {
    const totalSize = files.reduce((sum, file) => sum + file.size, 0);
    return `${files.length} 个文件 / ${formatSize(totalSize)}`;
  }, [files]);

  const jobSummary = useMemo(() => ({
    total: jobs.length,
    running: jobs.filter((job) => job.status === 'running' || job.status === 'queued').length,
    ready: jobs.filter((job) => job.status === 'ready').length,
    failed: jobs.filter((job) => job.status === 'failed').length,
    questions: jobs.reduce((sum, job) => sum + job.questionCount, 0),
    risks: jobs.reduce((sum, job) => sum + detectRisks(job.questions).length, 0),
  }), [jobs]);

  const updateJob = useCallback((jobId: string, patch: Partial<ImportJob>) => {
    setJobs((prev) => prev.map((job) => (job.id === jobId ? { ...job, ...patch } : job)));
  }, [setJobs]);

  const appendJobNote = useCallback((jobId: string, note: string) => {
    setJobs((prev) =>
      prev.map((job) => (job.id === jobId ? { ...job, notes: [...job.notes, note] } : job)),
    );
  }, [setJobs]);

  const addFiles = useCallback((incoming: FileList | File[]) => {
    const incomingFiles = Array.from(incoming);
    const accepted = incomingFiles.filter((file) => ACCEPTED_EXTS.includes(getExtension(file.name)));
    const unsupportedCount = incomingFiles.length - accepted.length;
    if (accepted.length === 0) {
      alert('请选择 Word、PDF、图片、Markdown 或纯文本文件。');
      return;
    }
    setFiles((prev) => {
      const seen = new Set(prev.map((file) => `${file.name}:${file.size}:${file.lastModified}`));
      const deduped = accepted.filter((file) => {
        const key = `${file.name}:${file.size}:${file.lastModified}`;
        if (seen.has(key)) return false;
        seen.add(key);
        return true;
      });
      const duplicateCount = accepted.length - deduped.length;
      const messages = [
        deduped.length > 0 ? `已加入 ${deduped.length} 个文件` : '',
        duplicateCount > 0 ? `跳过 ${duplicateCount} 个重复文件` : '',
        unsupportedCount > 0 ? `跳过 ${unsupportedCount} 个不支持的文件` : '',
      ].filter(Boolean);
      setImportMessage(messages.join('，'));
      if (deduped.length > 0) setDirectText('');
      return [...prev, ...deduped];
    });
  }, [setDirectText, setFiles, setImportMessage]);

  const buildRunnableFiles = useCallback((): File[] => {
    if (directText.trim()) {
      return [new File([directText.trim()], 'pasted-questions.md', { type: 'text/markdown' })];
    }
    return files;
  }, [directText, files]);

  const processJob = useCallback(
    async (job: ImportJob) => {
      updateJob(job.id, { status: 'running', step: 'upload', startedAt: Date.now(), error: undefined });

      try {
        const pipeline = guessPipeline(job.fileName);
        if (strategy === 'document' && pipeline === 'vision') {
          appendJobNote(job.id, '该文件更适合 OCR，已按自动分流继续处理。');
        }
        if (strategy === 'vision' && pipeline === 'document') {
          appendJobNote(job.id, '该文件更适合文档解析，已按自动分流继续处理。');
        }

        const batch = await createImportBatch(job.file);
        updateJob(job.id, {
          batchId: batch.batch_id,
          contentVersion: batch.content_version,
          step: 'preprocess',
        });
        appendJobNote(job.id, `批次已创建：${batch.batch_id}`);

        if (strategy === 'extract_images') {
          const extracted = await extractBatchImages(batch.batch_id);
          updateJob(job.id, {
            status: 'ready',
            step: 'review',
            mediaAssets: extracted.media_assets || [],
            imageCount: extracted.image_count || 0,
            questionCount: 0,
            finishedAt: Date.now(),
          });
          appendJobNote(job.id, `已提取 ${extracted.image_count || 0} 张图片，未生成题目草稿。`);
          return;
        }

        updateJob(job.id, { step: 'recognize' });
        appendJobNote(job.id, pipeline === 'vision' ? '进入 OCR / 视觉识别。' : '进入文档解析与结构化。');

        const recognized = await runImportBatchRecognize(batch.batch_id);
        const editable = ((recognized.questions ?? []) as RawQuestion[]).map(toEditable);
        const mediaAssets = recognized.media_assets || [];
        if (recognized.warnings?.length) {
          recognized.warnings.slice(0, 3).forEach((warning) => appendJobNote(job.id, `提示：${warning}`));
        }
        if (recognized.ai_refined_count) {
          appendJobNote(job.id, `AI 初校已调整 ${recognized.ai_refined_count} 道题。`);
        }

        updateJob(job.id, {
          step: 'risk_check',
          questions: editable,
          mediaAssets,
          questionCount: editable.length,
          imageCount: mediaAssets.length,
        });

        const risks = detectRisks(editable);
        if (risks.length > 0) {
          risks.forEach((risk) => appendJobNote(job.id, `风险：${risk}`));
        } else {
          appendJobNote(job.id, '未发现明显结构风险。');
        }

        updateJob(job.id, {
          status: 'ready',
          step: 'review',
          finishedAt: Date.now(),
        });
        appendJobNote(job.id, `识别完成：${editable.length} 道题，${mediaAssets.length} 张素材图。`);
      } catch (err) {
        updateJob(job.id, {
          status: 'failed',
          error: err instanceof Error ? err.message : '导入识别失败',
          finishedAt: Date.now(),
        });
      }
    },
    [appendJobNote, strategy, updateJob],
  );

  const handleStart = useCallback(async () => {
    const runnableFiles = buildRunnableFiles();
    if (runnableFiles.length === 0) return;

    const nextJobs: ImportJob[] = runnableFiles.map((file) => ({
      id: makeJobId(),
      file,
      fileName: file.name,
      status: 'queued',
      step: 'upload',
      questionCount: 0,
      imageCount: 0,
      questions: [],
      mediaAssets: [],
      notes: [],
    }));

    setJobs(nextJobs);

    await runWithConcurrency(nextJobs, IMPORT_CONCURRENCY, processJob);
  }, [buildRunnableFiles, processJob, setJobs]);

  const openInReviewCenter = useCallback(async (job: ImportJob) => {
    if (job.reviewTaskId) {
      navigate(`/review/${job.reviewTaskId}`);
      return;
    }
    if (!job.batchId || job.questions.length === 0) return;
    setSubmittingJobId(job.id);
    try {
      const payload = job.questions.map((q, index) => ({
        question_id: q.question_id || `${job.batchId}_q${String(index + 1).padStart(4, '0')}`,
        question_type: q.question_type,
        title: q.title,
        options: q.options,
        answer: q.answer,
        analysis: q.analysis,
        sub_questions: [],
        figures: q.figures,
        difficulty: null,
        knowledge_point: '',
        tags: [],
        source: job.fileName,
        import_batch_id: job.batchId,
      }));
      const result = await confirmImportBatch(job.batchId, payload, job.contentVersion, job.mediaAssets);
      setJobs((current) => current.map((item) => item.id === job.id ? { ...item, reviewTaskId: result.task_id } : item));
      navigate(`/review/${result.task_id}`);
    } catch (err) {
      alert(`进入校对中心失败：${err instanceof Error ? err.message : '未知错误'}`);
    } finally {
      setSubmittingJobId(null);
    }
  }, [navigate, setJobs]);

  return (
    <div className="h-full overflow-y-auto bg-[#f3f6fa] px-3 py-3 sm:px-5 sm:py-4">
      <div className="mx-auto grid max-w-[1280px] gap-4 xl:grid-cols-[1.25fr_0.75fr]">
        <section className="rounded-lg border border-[var(--color-border)] bg-white p-4 shadow-sm">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <div>
              <h1 className="text-base font-bold text-[var(--color-text)]">添加材料</h1>
              <p className="mt-1 text-xs text-[var(--color-text-muted)]">Word、PDF、图片、Markdown 或纯文本</p>
            </div>
            {persistedBatches.length > 0 && (
              <div className="rounded-md bg-[var(--color-bg-hover)] px-2.5 py-1.5 text-xs text-[var(--color-text-secondary)]">
                历史批次 {persistedBatches.length} · 最近 {persistedBatches[0].question_count} 题
              </div>
            )}
          </div>

          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept={ACCEPTED_EXTS.join(',')}
            className="hidden"
            onChange={(event) => {
              if (event.target.files) addFiles(event.target.files);
            }}
          />

          <div
            onDragOver={(event) => {
              event.preventDefault();
              setDragOver(true);
            }}
            onDragLeave={() => setDragOver(false)}
            onDrop={(event) => {
              event.preventDefault();
              setDragOver(false);
              addFiles(event.dataTransfer.files);
            }}
            onClick={() => fileInputRef.current?.click()}
            className="cursor-pointer rounded-md border-2 border-dashed p-5 text-center transition"
            style={{
              borderColor: dragOver ? 'var(--color-accent)' : 'var(--color-border-strong)',
              background: dragOver ? 'var(--color-accent-light)' : 'var(--color-bg-hover)',
            }}
          >
            <div className="text-sm font-semibold text-[var(--color-text)]">拖入文件，或点击选择</div>
            <div className="mt-1 text-xs text-[var(--color-text-muted)]">支持多选</div>
          </div>

          {importMessage && (
            <div className="mt-3 rounded-md border border-[var(--color-border)] bg-[var(--color-bg-hover)] px-3 py-2 text-xs text-[var(--color-text-secondary)]">
              {importMessage}
            </div>
          )}

          {files.length > 0 && (
            <div className="mt-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-card)] p-3">
              <div className="mb-2 flex items-center justify-between">
                <span className="text-sm font-semibold text-[var(--color-text)]">待处理材料</span>
                <span className="text-xs text-[var(--color-text-muted)]">{queuedSummary}</span>
              </div>
              <div className="space-y-2">
                {files.map((file, index) => (
                  <div key={`${file.name}-${index}`} className="flex items-center gap-2 rounded-md bg-[var(--color-bg-hover)] px-3 py-2">
                    <span className="min-w-0 flex-1 truncate text-sm text-[var(--color-text-secondary)]">{file.name}</span>
                    <span className="text-xs text-[var(--color-text-muted)]">{formatSize(file.size)}</span>
                    <button
                      type="button"
                      onClick={(event) => {
                        event.stopPropagation();
                        setPreviewFile(file);
                      }}
                      className="text-xs font-semibold text-[var(--color-accent)]"
                    >
                      检查
                    </button>
                    <button
                      type="button"
                      onClick={(event) => {
                        event.stopPropagation();
                        setFiles((prev) => prev.filter((_, itemIndex) => itemIndex !== index));
                      }}
                      className="text-xs font-semibold text-[var(--color-danger)]"
                    >
                      移除
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="my-4 flex items-center gap-3">
            <div className="h-px flex-1 bg-[var(--color-border)]" />
            <span className="text-xs text-[var(--color-text-muted)]">或直接粘贴文本</span>
            <div className="h-px flex-1 bg-[var(--color-border)]" />
          </div>

          {richTextEditorOpen ? (
            <Suspense fallback={<EditorLoading />}>
              <StructuredTextEditor
                value={directText}
                onChange={(value) => {
                  setDirectText(value);
                  if (value.trim()) setFiles([]);
                }}
                placeholder="粘贴题目文本；输入 / 可插入标题、列表、公式、表格和图片"
                minHeight={176}
              />
            </Suspense>
          ) : (
            <div className="rounded-md border border-[var(--color-border)] bg-[var(--color-bg-card)] p-3">
              <textarea
                value={directText}
                onChange={(event) => {
                  const value = event.target.value;
                  setDirectText(value);
                  if (value.trim()) setFiles([]);
                }}
                placeholder="粘贴题目文本；需要公式、表格或图片时可启用富文本编辑"
                className="min-h-44 w-full resize-y bg-transparent text-sm leading-6 text-[var(--color-text)] outline-none placeholder:text-[var(--color-text-muted)]"
              />
              <button
                type="button"
                onClick={() => setRichTextEditorOpen(true)}
                className="mt-2 text-xs font-semibold text-[var(--color-accent)]"
              >
                启用富文本编辑
              </button>
            </div>
          )}
        </section>

        <section className="rounded-lg border border-[var(--color-border)] bg-white p-4 shadow-sm">
          <h2 className="text-base font-bold text-[var(--color-text)]">处理设置</h2>
          <div className="mt-3 grid gap-2">
            {STRATEGIES.map((item) => {
              const active = strategy === item.value;
              return (
                <button
                  key={item.value}
                  onClick={() => setStrategy(item.value)}
                  className="rounded-md border px-3 py-2.5 text-left transition"
                  style={{
                    borderColor: active ? 'var(--color-accent)' : 'var(--color-border)',
                    background: active ? 'var(--color-accent-light)' : 'var(--color-bg-card)',
                  }}
                >
                  <div className="font-semibold text-[var(--color-text)]">{item.title}</div>
                  <div className="mt-0.5 line-clamp-1 text-xs text-[var(--color-text-muted)]">{item.desc}</div>
                </button>
              );
            })}
          </div>

          <div className="mt-4 flex gap-2 border-t border-[var(--color-border)] pt-4">
            <button
              onClick={() => void handleStart()}
              disabled={!canStart}
              className="rounded-md bg-[var(--color-accent)] px-5 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-40"
            >
              {hasRunningJobs ? '任务处理中...' : '开始处理'}
            </button>
            <button
              onClick={() => {
                setFiles([]);
                setDirectText('');
                setJobs([]);
              }}
              disabled={hasRunningJobs}
              className="rounded-md border border-[var(--color-border)] bg-[var(--color-bg-card)] px-4 py-2 text-sm font-semibold text-[var(--color-text-secondary)] disabled:opacity-40"
            >
              清空
            </button>
          </div>
        </section>

        <section className="rounded-lg border border-[var(--color-border)] bg-white p-4 shadow-sm xl:col-span-2">
          <div className="mb-3 flex items-center justify-between">
            <div>
              <h2 className="text-base font-bold text-[var(--color-text)]">处理记录</h2>
            </div>
            <span className="text-xs text-[var(--color-text-muted)]">
              {jobs.length > 0 ? `${jobs.length} 个任务` : '暂无任务'}
            </span>
          </div>

          {jobs.length > 0 && (
            <div className="mb-4 grid gap-2 text-xs sm:grid-cols-3 lg:grid-cols-6">
              <SummaryStat label="任务" value={jobSummary.total} />
              <SummaryStat label="处理中" value={jobSummary.running} />
              <SummaryStat label="待校对" value={jobSummary.ready} tone="success" />
              <SummaryStat label="失败" value={jobSummary.failed} tone="danger" />
              <SummaryStat label="题目" value={jobSummary.questions} />
              <SummaryStat label="风险类" value={jobSummary.risks} tone={jobSummary.risks > 0 ? 'danger' : undefined} />
            </div>
          )}

          {jobs.length === 0 ? (
            <div className="rounded-md border border-dashed border-[var(--color-border)] py-8 text-center text-sm text-[var(--color-text-muted)]">
              暂无处理任务
            </div>
          ) : (
            <div className="grid gap-3 lg:grid-cols-2">
              {jobs.map((job) => (
                <article key={job.id} className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-card)] p-4">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <h3 className="truncate text-sm font-bold text-[var(--color-text)]">{job.fileName}</h3>
                      <p className="mt-1 text-xs text-[var(--color-text-muted)]">
                        {job.status === 'ready'
                          ? `${job.questionCount} 道题 / ${job.imageCount} 张图`
                          : job.status === 'failed'
                            ? '处理失败'
                            : `正在处理：${STEPS.find((step) => step.key === job.step)?.label}`}
                      </p>
                      {job.startedAt && (
                        <p className="mt-0.5 text-[11px] text-[var(--color-text-muted)]">用时 {formatDuration(job.startedAt, job.finishedAt)}</p>
                      )}
                    </div>
                    <StatusPill status={job.status} />
                  </div>

                  <div className="mt-4 grid grid-cols-5 gap-1">
                    {STEPS.map((step) => {
                      const stepIndex = STEPS.findIndex((item) => item.key === step.key);
                      const currentIndex = STEPS.findIndex((item) => item.key === job.step);
                      const done = job.status === 'ready' || stepIndex < currentIndex;
                      const active = job.status === 'running' && step.key === job.step;
                      return (
                        <div
                          key={step.key}
                          className="h-1.5 rounded-full"
                          style={{
                            background: done
                              ? 'var(--color-success)'
                              : active
                                ? 'var(--color-accent)'
                                : 'var(--color-bg-hover)',
                          }}
                          title={step.label}
                        />
                      );
                    })}
                  </div>

                  {job.error && (
                    <div className="mt-3 rounded-md bg-[var(--color-danger-soft)] px-3 py-2 text-xs leading-5 text-[var(--color-danger)]">
                      {job.error}
                    </div>
                  )}

                  {job.notes.length > 0 && (
                    <div className="mt-3 space-y-1">
                      {job.notes.slice(-3).map((note, index) => (
                        <div key={`${note}-${index}`} className="text-xs leading-5 text-[var(--color-text-muted)]">
                          {note}
                        </div>
                      ))}
                    </div>
                  )}

                  <div className="mt-4 flex gap-2">
                    {job.status === 'ready' && job.questions.length > 0 && (
                      <button
                        onClick={() => void openInReviewCenter(job)}
                        disabled={submittingJobId === job.id}
                        className="rounded-md bg-[var(--color-accent)] px-3 py-1.5 text-sm font-semibold text-white disabled:opacity-50"
                      >
                        {submittingJobId === job.id ? '正在进入...' : '进入校对中心'}
                      </button>
                    )}
                    {job.status === 'failed' && (
                      <button
                        onClick={() => void processJob(job)}
                        className="rounded-md border border-[var(--color-border)] bg-[var(--color-bg-card)] px-3 py-1.5 text-sm font-semibold text-[var(--color-text-secondary)]"
                      >
                        重试此文件
                      </button>
                    )}
                  </div>
                </article>
              ))}
            </div>
          )}
        </section>
      </div>
      {previewFile && (
        <Suspense fallback={<PreviewLoading />}>
          <DocumentPreviewModal file={previewFile} onClose={() => setPreviewFile(null)} />
        </Suspense>
      )}
    </div>
  );
}

function SummaryStat({ label, value, tone }: { label: string; value: number; tone?: 'danger' | 'success' }) {
  const color = tone === 'danger' ? 'text-[var(--color-danger)]' : tone === 'success' ? 'text-[var(--color-success)]' : 'text-[var(--color-text)]';
  return (
    <div className="rounded-md border border-[var(--color-border)] bg-[var(--color-bg-hover)] px-3 py-2">
      <div className="text-[11px] text-[var(--color-text-muted)]">{label}</div>
      <div className={`mt-1 text-base font-bold ${color}`}>{value}</div>
    </div>
  );
}

function StatusPill({ status }: { status: JobStatus }) {
  const map: Record<JobStatus, { label: string; className: string }> = {
    queued: { label: '排队中', className: 'bg-[var(--color-bg-hover)] text-[var(--color-text-muted)]' },
    running: { label: '处理中', className: 'bg-[var(--color-accent-light)] text-[var(--color-accent)]' },
    ready: { label: '待校对', className: 'bg-[var(--color-success-soft)] text-[var(--color-success)]' },
    failed: { label: '失败', className: 'bg-[var(--color-danger-soft)] text-[var(--color-danger)]' },
  };
  const item = map[status];
  return <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${item.className}`}>{item.label}</span>;
}
