import { resolveServiceStatus } from './statusBarStatus';

interface Props {
  questionCount: number;
  lastImportTime?: string;
  mcpVlOnline: boolean;
  mcpLlmOnline: boolean;
  mcpRuntimeEnabled: boolean;
  mcpMode?: string;
  mcpVlModel?: string | null;
  mcpLlmModel?: string | null;
  mcpLastCheckedAt?: string | null;
  aiEnabled: boolean;
  taskProgress?: { running: number; total: number };
}

function StatusDot({
  online,
  runtimeEnabled,
  label,
  model,
  mode,
  lastCheckedAt,
}: {
  online: boolean;
  runtimeEnabled: boolean;
  label: string;
  model?: string | null;
  mode?: string;
  lastCheckedAt?: string | null;
}) {
  const status = resolveServiceStatus(online, runtimeEnabled, lastCheckedAt);
  const title = [
    `${label}: ${status.text}`,
    model ? `模型: ${model}` : '',
    mode ? `模式: ${mode}` : '',
    lastCheckedAt ? `检查: ${new Date(lastCheckedAt).toLocaleString()}` : '',
  ].filter(Boolean).join('\n');
  return (
    <span className="inline-flex items-center gap-1.5" title={title}>
      <span className={`inline-block h-1.5 w-1.5 rounded-full ${status.dotClass}`} />
      <span className="text-[11px]" style={{ color: status.colorToken }}>
        {label}: {status.text}
      </span>
    </span>
  );
}

export default function StatusBar({
  questionCount,
  lastImportTime,
  mcpVlOnline,
  mcpLlmOnline,
  mcpRuntimeEnabled,
  mcpMode,
  mcpVlModel,
  mcpLlmModel,
  mcpLastCheckedAt,
  aiEnabled,
  taskProgress,
}: Props) {
  return (
    <footer className="hidden h-6 flex-shrink-0 items-center gap-4 border-t border-[var(--color-border)] bg-[var(--color-bg-sidebar)] px-3 md:flex">
      <span className="text-[11px] text-[var(--color-text-muted)]">
        <span className="font-semibold text-[var(--color-text-secondary)]">{questionCount.toLocaleString()}</span>
        {' '}题库题目
      </span>

      {lastImportTime && (
        <span className="text-[11px] text-[var(--color-text-muted)]">
          最近导入：{lastImportTime}
        </span>
      )}

      {taskProgress && taskProgress.running > 0 && (
        <span className="text-[11px] font-medium text-[var(--color-accent)]">
          进行中 {taskProgress.running}/{taskProgress.total}
        </span>
      )}

      <div className="flex-1" />

      {aiEnabled ? (
        <div className="flex items-center gap-3">
          <StatusDot online={mcpVlOnline} runtimeEnabled={mcpRuntimeEnabled} label="VL" model={mcpVlModel} mode={mcpMode} lastCheckedAt={mcpLastCheckedAt} />
          <StatusDot online={mcpLlmOnline} runtimeEnabled={mcpRuntimeEnabled} label="LLM" model={mcpLlmModel} mode={mcpMode} lastCheckedAt={mcpLastCheckedAt} />
        </div>
      ) : (
        <span className="text-[11px] font-medium text-[var(--color-orange)]">
          AI 已关闭
        </span>
      )}
    </footer>
  );
}
