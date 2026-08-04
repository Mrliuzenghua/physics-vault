interface Props {
  questionCount: number;
  lastImportTime?: string;
  mcpVlOnline: boolean | null;
  mcpLlmOnline: boolean | null;
  mcpMode?: string;
  mcpVlModel?: string | null;
  mcpLlmModel?: string | null;
  mcpLastCheckedAt?: string | null;
  aiEnabled: boolean;
  taskProgress?: { running: number; total: number };
}

function StatusDot({
  online,
  label,
  model,
  mode,
  lastCheckedAt,
}: {
  online: boolean | null;
  label: string;
  model?: string | null;
  mode?: string;
  lastCheckedAt?: string | null;
}) {
  const isUnknown = online === null;
  const statusText = isUnknown ? '检查中' : online ? '在线' : '离线';
  const color = isUnknown ? 'var(--color-text-muted)' : online ? 'var(--color-green)' : 'var(--color-red)';
  const dotClass = isUnknown
    ? 'bg-[var(--color-text-muted)]'
    : online
      ? 'bg-[var(--color-green)]'
      : 'bg-[var(--color-red)]';
  const title = [
    `${label}: ${statusText}`,
    model ? `模型: ${model}` : '',
    mode ? `模式: ${mode}` : '',
    lastCheckedAt ? `检查: ${new Date(lastCheckedAt).toLocaleString()}` : '',
  ].filter(Boolean).join('\n');
  return (
    <span className="inline-flex items-center gap-1.5" title={title}>
      <span className={`inline-block h-1.5 w-1.5 rounded-full ${dotClass}`} />
      <span className="text-[11px]" style={{ color }}>
        {label}: {statusText}
      </span>
    </span>
  );
}

export default function StatusBar({
  questionCount,
  lastImportTime,
  mcpVlOnline,
  mcpLlmOnline,
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
        {' '}道题
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
          <StatusDot online={mcpVlOnline} label="VL" model={mcpVlModel} mode={mcpMode} lastCheckedAt={mcpLastCheckedAt} />
          <StatusDot online={mcpLlmOnline} label="LLM" model={mcpLlmModel} mode={mcpMode} lastCheckedAt={mcpLastCheckedAt} />
        </div>
      ) : (
        <span className="text-[11px] font-medium text-[var(--color-orange)]">
          AI 已关闭
        </span>
      )}
    </footer>
  );
}
