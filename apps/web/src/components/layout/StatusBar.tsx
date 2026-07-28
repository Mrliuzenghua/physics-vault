interface Props {
  questionCount: number;
  lastImportTime?: string;
  mcpVlOnline: boolean;
  mcpLlmOnline: boolean;
  aiEnabled: boolean;
  taskProgress?: { running: number; total: number };
}

function StatusDot({ online, label }: { online: boolean; label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className={`inline-block h-1.5 w-1.5 rounded-full ${online ? 'bg-[var(--color-green)]' : 'bg-[var(--color-red)]'}`} />
      <span className="text-[11px]" style={{ color: online ? 'var(--color-green)' : 'var(--color-red)' }}>
        {label}: {online ? '在线' : '离线'}
      </span>
    </span>
  );
}

export default function StatusBar({
  questionCount,
  lastImportTime,
  mcpVlOnline,
  mcpLlmOnline,
  aiEnabled,
  taskProgress,
}: Props) {
  return (
    <footer className="flex h-6 flex-shrink-0 items-center gap-4 border-t border-[var(--color-border)] bg-[var(--color-bg-sidebar)] px-3">
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
          <StatusDot online={mcpVlOnline} label="VL" />
          <StatusDot online={mcpLlmOnline} label="LLM" />
        </div>
      ) : (
        <span className="text-[11px] font-medium text-[var(--color-orange)]">
          AI 已关闭
        </span>
      )}
    </footer>
  );
}
