import { useCallback, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import ImportQuestionEditor, { type EditableQuestion } from '../components/import/ImportQuestionEditor';
import { normalizeShortInlineDisplayMath } from '../utils/mathText';
import {
  confirmImportBatch,
  createImportBatch,
  extractBatchImages,
  runImportBatchAiRefine,
  runImportBatchRecognize,
  uploadBatchImage,
} from '../services/api';
import type { ImportMediaAsset, Option, QuestionType } from '../types';

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

interface ImportJob {
  id: string;
  file: File;
  fileName: string;
  status: JobStatus;
  step: JobStep;
  batchId?: string;
  questionCount: number;
  imageCount: number;
  questions: EditableQuestion[];
  mediaAssets: ImportMediaAsset[];
  notes: string[];
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
  const risks: string[] = [];
  const emptyStem = questions.filter((q) => !q.title.trim()).length;
  const choiceWithoutOptions = questions.filter(
    (q) => (q.question_type === 'single_choice' || q.question_type === 'multi_choice') && q.options.length === 0,
  ).length;
  const noAnswer = questions.filter((q) => !q.answer.trim()).length;

  if (emptyStem > 0) risks.push(`${emptyStem} 道题题干为空`);
  if (choiceWithoutOptions > 0) risks.push(`${choiceWithoutOptions} 道选择题缺少选项`);
  if (noAnswer > 0) risks.push(`${noAnswer} 道题缺少答案`);
  return risks;
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

export default function ImportWorkbenchPage() {
  const navigate = useNavigate();
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const [files, setFiles] = useState<File[]>([]);
  const [directText, setDirectText] = useState('');
  const [strategy, setStrategy] = useState<ImportStrategy>('auto');
  const [jobs, setJobs] = useState<ImportJob[]>([]);
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [refining, setRefining] = useState(false);
  const [confirming, setConfirming] = useState(false);

  const activeJob = jobs.find((job) => job.id === activeJobId) ?? null;
  const hasRunningJobs = jobs.some((job) => job.status === 'running' || job.status === 'queued');
  const canStart = !hasRunningJobs && (files.length > 0 || directText.trim().length > 0);

  const queuedSummary = useMemo(() => {
    const totalSize = files.reduce((sum, file) => sum + file.size, 0);
    return `${files.length} 个文件 / ${formatSize(totalSize)}`;
  }, [files]);

  const updateJob = useCallback((jobId: string, patch: Partial<ImportJob>) => {
    setJobs((prev) => prev.map((job) => (job.id === jobId ? { ...job, ...patch } : job)));
  }, []);

  const appendJobNote = useCallback((jobId: string, note: string) => {
    setJobs((prev) =>
      prev.map((job) => (job.id === jobId ? { ...job, notes: [...job.notes, note] } : job)),
    );
  }, []);

  const addFiles = useCallback((incoming: FileList | File[]) => {
    const next = Array.from(incoming).filter((file) => ACCEPTED_EXTS.includes(getExtension(file.name)));
    if (next.length === 0) {
      alert('请选择 Word、PDF、图片、Markdown 或纯文本文件。');
      return;
    }
    setFiles((prev) => [...prev, ...next]);
    setDirectText('');
  }, []);

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
        updateJob(job.id, { batchId: batch.batch_id, step: 'preprocess' });
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
    setActiveJobId(null);
    setSelectedKey(null);

    await runWithConcurrency(nextJobs, IMPORT_CONCURRENCY, processJob);
  }, [buildRunnableFiles, processJob]);

  const openJobForReview = useCallback((job: ImportJob) => {
    setActiveJobId(job.id);
    setSelectedKey(job.questions[0]?._key ?? null);
  }, []);

  const handleChangeQuestion = useCallback((key: string, patch: Partial<EditableQuestion>) => {
    if (!activeJob) return;
    setJobs((prev) =>
      prev.map((job) =>
        job.id === activeJob.id
          ? { ...job, questions: job.questions.map((q) => (q._key === key ? { ...q, ...patch } : q)) }
          : job,
      ),
    );
  }, [activeJob]);

  const handleDeleteQuestion = useCallback((key: string) => {
    if (!activeJob) return;
    setJobs((prev) =>
      prev.map((job) => {
        if (job.id !== activeJob.id) return job;
        const idx = job.questions.findIndex((q) => q._key === key);
        const nextQuestions = job.questions.filter((q) => q._key !== key);
        setSelectedKey((current) => {
          if (current !== key) return current;
          return nextQuestions[Math.min(idx, nextQuestions.length - 1)]?._key ?? null;
        });
        return { ...job, questions: nextQuestions, questionCount: nextQuestions.length };
      }),
    );
  }, [activeJob]);

  const handleMergeWithNext = useCallback((key: string) => {
    if (!activeJob) return;
    setJobs((prev) =>
      prev.map((job) => {
        if (job.id !== activeJob.id) return job;
        const idx = job.questions.findIndex((q) => q._key === key);
        if (idx < 0 || idx >= job.questions.length - 1) return job;
        const current = job.questions[idx];
        const next = job.questions[idx + 1];
        const merged: EditableQuestion = {
          ...current,
          title: `${current.title.trimEnd()}\n${next.title.trim()}`,
          options: current.options.length > 0 ? current.options : next.options,
          answer: [current.answer, next.answer].filter((item) => item.trim()).join('\n'),
          analysis: [current.analysis, next.analysis].filter((item) => item.trim()).join('\n'),
          figures: [...current.figures, ...next.figures],
        };
        const nextQuestions = [...job.questions];
        nextQuestions.splice(idx, 2, merged);
        return { ...job, questions: nextQuestions, questionCount: nextQuestions.length };
      }),
    );
  }, [activeJob]);

  const handleUploadImage = useCallback(async (imageFile: File): Promise<ImportMediaAsset> => {
    if (!activeJob?.batchId) throw new Error('当前批次尚未创建，不能上传图片。');
    const asset = await uploadBatchImage(activeJob.batchId, imageFile);
    setJobs((prev) =>
      prev.map((job) =>
        job.id === activeJob.id
          ? { ...job, mediaAssets: [...job.mediaAssets, asset], imageCount: job.imageCount + 1 }
          : job,
      ),
    );
    return asset;
  }, [activeJob]);

  const handleAiRefine = useCallback(async () => {
    if (!activeJob?.batchId || activeJob.questions.length === 0) return;
    setRefining(true);
    try {
      const payload = activeJob.questions.map((q) => ({
        question_id: q.question_id,
        question_type: q.question_type,
        title: q.title,
        options: q.options,
        answer: q.answer,
        analysis: q.analysis,
      }));
      const result = await runImportBatchAiRefine(activeJob.batchId, payload);
      const refined = (result.questions ?? []) as RawQuestion[];
      if (refined.length === activeJob.questions.length) {
        setJobs((prev) =>
          prev.map((job) =>
            job.id === activeJob.id
              ? {
                  ...job,
                  questions: refined.map((raw, index) => ({
                    ...toEditable(raw),
                    _key: job.questions[index]._key,
                    figures: job.questions[index].figures,
                    _aiRefined: true,
                  })),
                  notes: [...job.notes, `AI 初校完成：${result.refined_count} 道题被调整。`],
                }
              : job,
          ),
        );
      }
    } catch (err) {
      alert(`AI 初校失败：${err instanceof Error ? err.message : '未知错误'}`);
    } finally {
      setRefining(false);
    }
  }, [activeJob]);

  const handleSendToReview = useCallback(async () => {
    if (!activeJob?.batchId || activeJob.questions.length === 0) return;
    setConfirming(true);
    try {
      const payload = activeJob.questions.map((q, index) => ({
        question_id: q.question_id || `${activeJob.batchId}_q${String(index + 1).padStart(4, '0')}`,
        question_type: q.question_type,
        title: q.title,
        options: q.options,
        answer: q.answer,
        analysis: q.analysis,
        sub_questions: [],
        figures: q.figures,
        difficulty: 0,
        knowledge_point: '',
        tags: [],
        source: activeJob.fileName,
        import_batch_id: activeJob.batchId,
      }));
      const result = await confirmImportBatch(activeJob.batchId, payload);
      navigate(`/review/${result.task_id}`);
    } catch (err) {
      alert(`送入校对中心失败：${err instanceof Error ? err.message : '未知错误'}`);
    } finally {
      setConfirming(false);
    }
  }, [activeJob, navigate]);

  if (activeJob) {
    return (
      <div className="flex h-full flex-col bg-[var(--color-bg)]">
        <div className="flex flex-wrap items-center gap-2 border-b border-[var(--color-border)] bg-[var(--color-bg-card)] px-5 py-3">
          <button
            onClick={() => setActiveJobId(null)}
            className="rounded-md border border-[var(--color-border)] bg-[var(--color-bg-card)] px-3 py-1.5 text-sm text-[var(--color-text-secondary)]"
          >
            返回任务列表
          </button>
          <div>
            <h1 className="text-base font-bold text-[var(--color-text)]">{activeJob.fileName}</h1>
            <p className="text-xs text-[var(--color-text-muted)]">
              {activeJob.questionCount} 道题 / {activeJob.imageCount} 张素材图 / 批次 {activeJob.batchId}
            </p>
          </div>
          <div className="flex-1" />
          <button
            onClick={handleAiRefine}
            disabled={refining || activeJob.questions.length === 0}
            className="rounded-md border border-[var(--color-purple)] bg-[var(--color-purple-light)] px-3 py-1.5 text-sm font-semibold text-[var(--color-purple)] disabled:opacity-50"
          >
            {refining ? 'AI 初校中...' : '重跑 AI 初校'}
          </button>
          <button
            onClick={handleSendToReview}
            disabled={confirming || activeJob.questions.length === 0}
            className="rounded-md bg-[var(--color-accent)] px-4 py-1.5 text-sm font-semibold text-white disabled:opacity-50"
          >
            {confirming ? '提交中...' : '送入校对中心'}
          </button>
        </div>

        <div className="min-h-0 flex-1">
          <ImportQuestionEditor
            questions={activeJob.questions}
            selectedKey={selectedKey}
            onSelect={setSelectedKey}
            onChange={handleChangeQuestion}
            onDelete={handleDeleteQuestion}
            onMergeWithNext={handleMergeWithNext}
            mediaAssets={activeJob.mediaAssets}
            onUploadImage={handleUploadImage}
          />
        </div>
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto bg-[var(--color-bg)] px-6 py-5">
      <div className="mx-auto grid max-w-7xl gap-5 xl:grid-cols-[1.1fr_0.9fr]">
        <section className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-card)] p-5 shadow-sm">
          <div className="mb-4">
            <h1 className="text-xl font-bold text-[var(--color-text)]">导入识别</h1>
            <p className="mt-2 text-sm leading-6 text-[var(--color-text-secondary)]">
              把导入拆成多个可恢复的小任务。每个文件独立处理，并发推进；某个文件失败不会拖住整批材料。
            </p>
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
            className="cursor-pointer rounded-lg border-2 border-dashed p-8 text-center transition"
            style={{
              borderColor: dragOver ? 'var(--color-accent)' : 'var(--color-border-strong)',
              background: dragOver ? 'var(--color-accent-light)' : 'var(--color-bg-hover)',
            }}
          >
            <div className="text-base font-semibold text-[var(--color-text)]">拖入文件，或点击选择</div>
            <div className="mt-2 text-sm text-[var(--color-text-muted)]">
              支持 Word、PDF、图片、Markdown、纯文本。可以一次选择多个文件。
            </div>
          </div>

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

          <div className="my-5 flex items-center gap-3">
            <div className="h-px flex-1 bg-[var(--color-border)]" />
            <span className="text-xs text-[var(--color-text-muted)]">或直接粘贴文本</span>
            <div className="h-px flex-1 bg-[var(--color-border)]" />
          </div>

          <textarea
            value={directText}
            onChange={(event) => {
              setDirectText(event.target.value);
              if (event.target.value.trim()) setFiles([]);
            }}
            rows={8}
            placeholder="粘贴题目原文。粘贴文本会作为一个独立导入任务处理。"
            className="w-full resize-y rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-card)] p-3 text-sm leading-7 text-[var(--color-text)] outline-none"
          />
        </section>

        <section className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-card)] p-5 shadow-sm">
          <h2 className="text-base font-bold text-[var(--color-text)]">识别策略</h2>
          <div className="mt-4 grid gap-3">
            {STRATEGIES.map((item) => {
              const active = strategy === item.value;
              return (
                <button
                  key={item.value}
                  onClick={() => setStrategy(item.value)}
                  className="rounded-lg border p-4 text-left transition"
                  style={{
                    borderColor: active ? 'var(--color-accent)' : 'var(--color-border)',
                    background: active ? 'var(--color-accent-light)' : 'var(--color-bg-card)',
                  }}
                >
                  <div className="font-semibold text-[var(--color-text)]">{item.title}</div>
                  <div className="mt-1 text-sm leading-6 text-[var(--color-text-muted)]">{item.desc}</div>
                </button>
              );
            })}
          </div>

          <div className="mt-5 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-hover)] p-4">
            <h3 className="text-sm font-bold text-[var(--color-text)]">执行阶段</h3>
            <div className="mt-3 space-y-3">
              {STEPS.map((step, index) => (
                <div key={step.key} className="flex gap-3">
                  <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-[var(--color-bg-card)] text-xs font-bold text-[var(--color-accent)]">
                    {index + 1}
                  </span>
                  <div>
                    <div className="text-sm font-semibold text-[var(--color-text)]">{step.label}</div>
                    <div className="text-xs text-[var(--color-text-muted)]">{step.desc}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="mt-5 flex gap-2">
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
                setActiveJobId(null);
              }}
              disabled={hasRunningJobs}
              className="rounded-md border border-[var(--color-border)] bg-[var(--color-bg-card)] px-4 py-2 text-sm font-semibold text-[var(--color-text-secondary)] disabled:opacity-40"
            >
              清空
            </button>
          </div>
        </section>

        <section className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-card)] p-5 shadow-sm xl:col-span-2">
          <div className="mb-4 flex items-center justify-between">
            <div>
              <h2 className="text-base font-bold text-[var(--color-text)]">任务进度与最近结果</h2>
              <p className="mt-1 text-sm text-[var(--color-text-muted)]">
                每个文件独立推进，最多同时处理 2 个任务。失败项可以单独重试，已完成项可以直接进入校对。
              </p>
            </div>
            <span className="text-xs text-[var(--color-text-muted)]">
              {jobs.length > 0 ? `${jobs.length} 个任务` : '暂无任务'}
            </span>
          </div>

          {jobs.length === 0 ? (
            <div className="rounded-lg border border-dashed border-[var(--color-border)] py-10 text-center text-sm text-[var(--color-text-muted)]">
              选择材料并点击“开始处理”后，这里会显示每个文件的阶段状态。
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
                        onClick={() => openJobForReview(job)}
                        className="rounded-md bg-[var(--color-accent)] px-3 py-1.5 text-sm font-semibold text-white"
                      >
                        校对本批
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
