import type { FileTaskState, Question } from '../../types';
import LatexRenderer from '../render/LatexRenderer';

const STATUS_LABELS: Record<string, string> = {
  pending: '等待中',
  running: '运行中',
  completed: '已完成',
  failed: '失败',
};

const STATUS_COLORS: Record<string, string> = {
  pending: 'var(--color-text-muted)',
  running: 'var(--color-accent)',
  completed: 'var(--color-green)',
  failed: 'var(--color-red)',
};

const STATUS_BG: Record<string, string> = {
  pending: 'var(--color-bg-hover)',
  running: 'var(--color-accent-light)',
  completed: 'var(--color-green-light)',
  failed: 'var(--color-red-light)',
};

const STEP_LABELS: Record<string, string> = {
  convert: '转换',
  clean: '清洗',
  parse: '切题',
  ai_parse: 'AI 识别',
};

interface Props {
  task: FileTaskState;
  onCopyResult: (task: FileTaskState) => void;
  onEnterReview: (taskId: string) => void;
  onRetry: (task: FileTaskState) => void;
}

/** Safely extract a string value from the task result dict. */
function resultStr(result: Record<string, unknown> | null | undefined, key: string): string | undefined {
  if (result == null) return undefined;
  const value = result[key];
  if (value == null) return undefined;
  return String(value);
}

// ── Preview helpers ──

interface ConvertPreview {
  outputPath?: string;
  textPreview?: string;
}

interface CleanPreview {
  origLen?: number;
  newLen?: number;
  textPreview?: string;
}

interface ParsePreview {
  questionCount?: number;
  firstQuestionTitle?: string;
}

function getConvertPreview(task: FileTaskState): ConvertPreview {
  const result = task.convertTask?.result;
  const text = resultStr(result, 'text');
  return {
    outputPath: resultStr(result, 'output_path'),
    textPreview: text != null && text.trim().length > 0 ? text.slice(0, 150) : undefined,
  };
}

function getCleanPreview(task: FileTaskState): CleanPreview {
  const result = task.cleanTask?.result;
  const text = resultStr(result, 'cleaned_text');
  return {
    origLen: result?.original_length as number | undefined,
    newLen: result?.cleaned_length as number | undefined,
    textPreview: text != null && text.trim().length > 0 ? text.slice(0, 200) : undefined,
  };
}

function getParsePreview(task: FileTaskState): ParsePreview {
  const result = task.parseTask?.result;
  const questions = result?.questions as Array<{ title?: string }> | undefined;
  const firstTitle = questions != null && questions.length > 0 ? questions[0].title : undefined;
  return {
    questionCount: result?.question_count as number | undefined,
    firstQuestionTitle: firstTitle != null && firstTitle.trim().length > 0 ? firstTitle.slice(0, 150) : undefined,
  };
}

interface AiParsePreview {
  documentType?: string;
  pageCount?: number;
  questionCount?: number;
  firstQuestionTitle?: string;
}

function getAiParsePreview(task: FileTaskState): AiParsePreview {
  const result = task.aiParseTask?.result;
  const questions = result?.questions as Array<{ title?: string }> | undefined;
  const firstTitle = questions != null && questions.length > 0 ? questions[0].title : undefined;
  return {
    documentType: result?.document_type as string | undefined,
    pageCount: result?.page_count as number | undefined,
    questionCount: result?.question_count as number | undefined,
    firstQuestionTitle: firstTitle != null && firstTitle.trim().length > 0 ? firstTitle.slice(0, 150) : undefined,
  };
}

function getRecognizedQuestions(task: FileTaskState): Question[] {
  const parseQuestions = task.parseTask?.result?.questions;
  const aiQuestions = task.aiParseTask?.result?.questions;
  if (Array.isArray(parseQuestions)) return parseQuestions as Question[];
  if (Array.isArray(aiQuestions)) return aiQuestions as Question[];
  return [];
}

export default function TaskCard({ task, onCopyResult, onEnterReview, onRetry }: Props) {
  const statusLabel = STATUS_LABELS[task.status] || '未知';
  const statusColor = STATUS_COLORS[task.status] || 'var(--color-text-muted)';
  const statusBg = STATUS_BG[task.status] || 'var(--color-bg-hover)';

  const hasCompletedParse = task.parseTask?.status === 'completed' || task.aiParseTask?.status === 'completed';
  const hasAnyResult = task.convertTask || task.cleanTask || task.parseTask || task.aiParseTask;
  const isAiMode = task.currentStep === 'ai_parse' || task.aiParseTask != null;

  const convertPreview = getConvertPreview(task);
  const cleanPreview = getCleanPreview(task);
  const parsePreview = getParsePreview(task);
  const aiParsePreview = getAiParsePreview(task);
  const recognizedQuestions = getRecognizedQuestions(task);

  return (
    <div
      className="rounded-lg border p-3 transition-colors"
      style={{
        background: 'var(--color-bg-card)',
        borderColor: task.status === 'running' ? 'var(--color-accent)' : 'var(--color-border)',
        boxShadow: 'var(--shadow-card)',
        opacity: task.status === 'pending' ? 0.7 : 1,
      }}
    >
      {/* Header */}
      <div className="mb-2 flex items-center justify-between">
        <div className="flex items-center gap-2 min-w-0">
          <span className="truncate text-sm font-medium" style={{ color: 'var(--color-text)' }}>
            {task.fileName}
          </span>
          <span
            className="shrink-0 rounded-full px-2 py-0.5 text-xs font-medium"
            style={{ background: statusBg, color: statusColor }}
          >
            {statusLabel}
          </span>
        </div>
      </div>

      {/* Step Indicators */}
      <div className="mb-2 flex items-center gap-1 text-xs">
        {isAiMode ? (
          (() => {
            const aiDone = task.aiParseTask?.status === 'completed';
            const aiFailed = task.aiParseTask?.status === 'failed';
            const aiRunning = task.status === 'running' || task.aiParseTask?.status === 'running';
            let dotColor = 'var(--color-border)';
            if (aiDone) dotColor = 'var(--color-green)';
            else if (aiFailed) dotColor = 'var(--color-red)';
            else if (aiRunning) dotColor = 'var(--color-accent)';
            return (
              <div className="flex items-center gap-1">
                <span
                  className="inline-block h-2 w-2 rounded-full"
                  style={{ background: dotColor, animation: aiRunning ? 'pulse 1.5s infinite' : undefined }}
                />
                <span style={{ color: aiDone ? 'var(--color-green)' : aiFailed ? 'var(--color-red)' : 'var(--color-text-muted)' }}>
                  {STEP_LABELS.ai_parse}
                </span>
              </div>
            );
          })()
        ) : (
          (['convert', 'clean', 'parse'] as const).map((step, index) => {
            const stepTask = step === 'convert' ? task.convertTask : step === 'clean' ? task.cleanTask : task.parseTask;
            const stepDone = stepTask?.status === 'completed';
            const stepFailed = stepTask?.status === 'failed';
            const stepRunning = stepTask?.status === 'running';
            let dotColor = 'var(--color-border)';
            if (stepDone) dotColor = 'var(--color-green)';
            if (stepFailed) dotColor = 'var(--color-red)';
            if (stepRunning) dotColor = 'var(--color-accent)';
            return (
              <div key={step} className="flex items-center gap-1">
                <span
                  className="inline-block h-2 w-2 rounded-full"
                  style={{ background: dotColor, animation: stepRunning ? 'pulse 1.5s infinite' : undefined }}
                />
                <span style={{ color: stepDone ? 'var(--color-green)' : 'var(--color-text-muted)' }}>
                  {STEP_LABELS[step]}
                </span>
                {index < 2 && <span className="mx-0.5" style={{ color: 'var(--color-border)' }}>{' → '}</span>}
              </div>
            );
          })
        )}
      </div>

      {/* Error messages — only shown when the task is in a failed state */}
      {task.status === 'failed' && (
        <>
          {task.error && (
            <div
              className="mb-2 rounded p-2 text-xs whitespace-pre-wrap"
              style={{ background: 'var(--color-red-light)', color: 'var(--color-red)' }}
            >
              {task.error}
            </div>
          )}
          {task.convertTask?.error && !task.error && (
            <div
              className="mb-2 rounded p-2 text-xs"
              style={{ background: 'var(--color-red-light)', color: 'var(--color-red)' }}
            >
              {'转换错误: '}
              {task.convertTask.error}
            </div>
          )}
          {task.cleanTask?.error && !task.error && (
            <div
              className="mb-2 rounded p-2 text-xs"
              style={{ background: 'var(--color-red-light)', color: 'var(--color-red)' }}
            >
              {'清洗错误: '}
              {task.cleanTask.error}
            </div>
          )}
          {task.parseTask?.error && !task.error && (
            <div
              className="mb-2 rounded p-2 text-xs"
              style={{ background: 'var(--color-red-light)', color: 'var(--color-red)' }}
            >
              {'切题错误: '}
              {task.parseTask.error}
            </div>
          )}
          {task.aiParseTask?.error && !task.error && (
            <div
              className="mb-2 rounded p-2 text-xs"
              style={{ background: 'var(--color-red-light)', color: 'var(--color-red)' }}
            >
              {'AI 识别错误: '}
              {task.aiParseTask.error}
            </div>
          )}
        </>
      )}

      {/* Result Summary — priority: ai_parse > parse > clean > convert */}
      {hasAnyResult && (
        <div className="mb-2 space-y-2 text-xs">
          {/* ── AI Parse result (highest priority) ── */}
          {task.aiParseTask?.status === 'completed' && (
            <div>
              <div className="mb-0.5 font-medium" style={{ color: 'var(--color-text-muted)' }}>
                AI 识别结果
              </div>
              {aiParsePreview.questionCount !== undefined && (
                <div className="mb-0.5" style={{ color: 'var(--color-text-secondary)' }}>
                  题目数量：<span className="font-semibold" style={{ color: 'var(--color-accent-dark)' }}>{aiParsePreview.questionCount}</span>
                  {aiParsePreview.documentType && ` · ${aiParsePreview.documentType}`}
                  {aiParsePreview.pageCount != null && ` · ${aiParsePreview.pageCount}页`}
                </div>
              )}
              {aiParsePreview.firstQuestionTitle ? (
                <div>
                  <div className="mb-0.5" style={{ color: 'var(--color-text-muted)' }}>首题预览</div>
                  <div className="max-h-12 overflow-hidden rounded p-1.5 whitespace-pre-wrap"
                    style={{ background: 'var(--color-bg-code)', color: 'var(--color-text-secondary)', fontFamily: 'monospace' }}>
                    {aiParsePreview.firstQuestionTitle}
                  </div>
                </div>
              ) : (
                <div style={{ color: 'var(--color-text-muted)' }}>暂无可预览内容</div>
              )}
            </div>
          )}

          {/* ── Parse result ── */}
          {task.parseTask?.status === 'completed' && (
            <div>
              <div className="mb-0.5 font-medium" style={{ color: 'var(--color-text-muted)' }}>
                切题结果
              </div>
              {parsePreview.questionCount !== undefined && (
                <div className="mb-0.5" style={{ color: 'var(--color-text-secondary)' }}>
                  题目数量：
                  <span className="font-semibold" style={{ color: 'var(--color-accent-dark)' }}>
                    {parsePreview.questionCount}
                  </span>
                </div>
              )}
              {parsePreview.firstQuestionTitle !== undefined ? (
                <div>
                  <div className="mb-0.5" style={{ color: 'var(--color-text-muted)' }}>
                    第一题预览
                  </div>
                  <div
                    className="max-h-12 overflow-hidden rounded p-1.5 whitespace-pre-wrap"
                    style={{
                      background: 'var(--color-bg-code)',
                      color: 'var(--color-text-secondary)',
                      fontFamily: 'monospace',
                    }}
                  >
                    {parsePreview.firstQuestionTitle}
                    {parsePreview.firstQuestionTitle.length >= 150 ? '…' : ''}
                  </div>
                </div>
              ) : (
                <div style={{ color: 'var(--color-text-muted)' }}>
                  暂无可预览内容
                </div>
              )}
            </div>
          )}

          {/* ── Clean result ── */}
          {task.cleanTask?.status === 'completed' && (
            <div>
              <div className="mb-0.5 font-medium" style={{ color: 'var(--color-text-muted)' }}>
                清洗结果
                {cleanPreview.origLen !== undefined && cleanPreview.newLen !== undefined
                  ? `（${cleanPreview.origLen} → ${cleanPreview.newLen} 字符）`
                  : ''}
              </div>
              {cleanPreview.textPreview !== undefined ? (
                <div
                  className="max-h-16 overflow-y-auto rounded p-1.5 whitespace-pre-wrap"
                  style={{
                    background: 'var(--color-bg-code)',
                    color: 'var(--color-text-secondary)',
                    fontFamily: 'monospace',
                  }}
                >
                  {cleanPreview.textPreview}
                  {cleanPreview.textPreview.length >= 200 ? '…' : ''}
                </div>
              ) : (
                <div style={{ color: 'var(--color-text-muted)' }}>
                  暂无可预览内容
                </div>
              )}
            </div>
          )}

          {/* ── Convert result (lowest priority) ── */}
          {task.convertTask?.status === 'completed' &&
            !task.cleanTask?.status &&
            !task.parseTask?.status && (
            <div>
              <div className="mb-0.5 font-medium" style={{ color: 'var(--color-text-muted)' }}>
                转换结果
              </div>
              {convertPreview.outputPath !== undefined && (
                <div className="mb-0.5" style={{ color: 'var(--color-text-secondary)' }}>
                  输出文件：
                  <span style={{ color: 'var(--color-text)', fontFamily: 'monospace' }}>
                    {convertPreview.outputPath}
                  </span>
                </div>
              )}
              {convertPreview.textPreview !== undefined ? (
                <div
                  className="max-h-12 overflow-hidden rounded p-1.5 whitespace-pre-wrap"
                  style={{
                    background: 'var(--color-bg-code)',
                    color: 'var(--color-text-secondary)',
                    fontFamily: 'monospace',
                  }}
                >
                  {convertPreview.textPreview}
                  {convertPreview.textPreview.length >= 150 ? '…' : ''}
                </div>
              ) : (
                <div style={{ color: 'var(--color-text-muted)' }}>
                  暂无可预览内容
                </div>
              )}
            </div>
          )}

          {/* ── Fallback: results exist but all statuses are non-completed (e.g. failed) ── */}
          {task.convertTask?.status !== 'completed' &&
            task.cleanTask?.status !== 'completed' &&
            task.parseTask?.status !== 'completed' && (
            <div style={{ color: 'var(--color-text-muted)' }}>
              暂无可预览内容
            </div>
          )}
        </div>
      )}

      {recognizedQuestions.length > 0 && (
        <RecognizedQuestionPreview questions={recognizedQuestions} />
      )}

      {/* Actions */}
      {task.status === 'completed' && (
        <div className="flex items-center gap-2 border-t pt-2" style={{ borderColor: 'var(--color-border)' }}>
          <button
            onClick={() => onCopyResult(task)}
            className="cursor-pointer rounded px-2.5 py-1 text-xs font-medium transition-colors"
            style={{ background: 'var(--color-bg-hover)', color: 'var(--color-text-secondary)' }}
          >
            {'复制结果 JSON'}
          </button>
          {hasCompletedParse && (
            <button
              onClick={() => onEnterReview((task.parseTask || task.aiParseTask)?.task_id || '')}
              className="cursor-pointer rounded px-2.5 py-1 text-xs font-medium text-white transition-colors"
              style={{ background: 'var(--color-accent)' }}
            >
              {'进入校对页'}
            </button>
          )}
        </div>
      )}

      {task.status === 'failed' && (
        <div className="flex items-center gap-2 border-t pt-2" style={{ borderColor: 'var(--color-border)' }}>
          <button
            onClick={() => onRetry(task)}
            className="cursor-pointer rounded px-2.5 py-1 text-xs font-medium text-white transition-colors"
            style={{ background: 'var(--color-accent)' }}
          >
            {'重试'}
          </button>
        </div>
      )}
    </div>
  );
}

function RecognizedQuestionPreview({ questions }: { questions: Question[] }) {
  return (
    <div className="mb-3 space-y-2 border-t pt-3" style={{ borderColor: 'var(--color-border)' }}>
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold" style={{ color: 'var(--color-text-muted)' }}>
          导入识别题目预览
        </span>
        <span className="rounded px-2 py-0.5 text-xs" style={{ background: 'var(--color-accent-light)', color: 'var(--color-accent)' }}>
          {questions.length} 题
        </span>
      </div>
      <div className="max-h-[520px] space-y-3 overflow-y-auto pr-1">
        {questions.map((question, index) => (
          <div
            key={question.question_id || index}
            className="rounded-lg border p-3"
            style={{ borderColor: 'var(--color-border)', background: 'var(--color-bg)' }}
          >
            <div className="mb-2 flex items-center gap-2">
              <span
                className="rounded px-2 py-0.5 text-xs font-semibold text-white"
                style={{ background: 'var(--color-accent)' }}
              >
                第 {index + 1} 题
              </span>
              <span className="text-xs" style={{ color: 'var(--color-text-muted)' }}>
                {question.question_type || '未判定题型'}
              </span>
            </div>

            <div className="text-sm leading-relaxed" style={{ color: 'var(--color-text)' }}>
              <LatexRenderer text={question.title || '（无题干）'} />
            </div>

            {Array.isArray(question.figures) && question.figures.length > 0 && (
              <div className="mt-3 grid gap-2" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))' }}>
                {question.figures.map((fig, figIndex) => (
                  <div key={fig.fig_uuid || figIndex} className="rounded border p-2" style={{ borderColor: 'var(--color-border)', background: 'var(--color-bg-card)' }}>
                    {fig.local_path ? (
                      <img
                        src={`/files/${fig.local_path}`}
                        alt={fig.fig_uuid || `figure-${figIndex + 1}`}
                        className="max-h-48 w-full object-contain"
                      />
                    ) : (
                      <div className="text-xs" style={{ color: 'var(--color-text-muted)' }}>图片路径缺失</div>
                    )}
                    <div className="mt-1 truncate text-xs" style={{ color: 'var(--color-text-muted)' }}>
                      {fig.fig_uuid || fig.local_path}
                    </div>
                  </div>
                ))}
              </div>
            )}

            {Array.isArray(question.options) && question.options.length > 0 && (
              <div className="mt-3 grid gap-2" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))' }}>
                {question.options.map((option, optionIndex) => (
                  <div key={`${option.opt}-${optionIndex}`} className="rounded border p-2 text-sm" style={{ borderColor: 'var(--color-border)', background: 'var(--color-bg-card)' }}>
                    <span className="mr-2 font-semibold" style={{ color: 'var(--color-accent)' }}>{option.opt}.</span>
                    <LatexRenderer text={option.content} />
                  </div>
                ))}
              </div>
            )}

            {(question.answer || question.analysis) && (
              <div className="mt-3 rounded border p-2" style={{ borderColor: 'var(--color-green)', background: 'var(--color-green-light)' }}>
                {question.answer && (
                  <div className="mb-2 text-sm" style={{ color: 'var(--color-green)' }}>
                    <span className="font-semibold">答案：</span>
                    <LatexRenderer text={String(question.answer)} />
                  </div>
                )}
                {question.analysis && (
                  <div className="text-sm" style={{ color: 'var(--color-text-secondary)' }}>
                    <span className="font-semibold">解析：</span>
                    <LatexRenderer text={String(question.analysis)} />
                  </div>
                )}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
