import type { ReactNode } from 'react';
import type { Question } from '../../types';
import QuestionLiveEditor from './QuestionLiveEditor';

interface Props {
  question: Question;
  onChange: (patch: Partial<Question>) => void;
  onClose: () => void;
  onSave?: () => void | Promise<void>;
  saving?: boolean;
  title?: string;
  subtitle?: string;
  footer?: ReactNode;
}

export default function QuestionEditorModal({
  question,
  onChange,
  onClose,
  onSave,
  saving = false,
  title = '实时编辑题目',
  subtitle = '编辑内容会即时同步到预览，关闭后仍可继续浏览题库。',
  footer,
}: Props) {
  return (
    <div className="fixed inset-0 z-[80] flex items-center justify-center bg-slate-950/55 p-4 backdrop-blur-[2px]" role="dialog" aria-modal="true" aria-label={title}>
      <button type="button" aria-label="关闭弹窗" className="absolute inset-0 cursor-default" onClick={onClose} />
      <div className="relative z-10 flex max-h-[min(900px,calc(100vh-32px))] w-[min(1420px,calc(100vw-32px))] flex-col overflow-hidden rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-card)] shadow-2xl">
        <header className="flex shrink-0 items-center justify-between gap-4 border-b border-[var(--color-border)] bg-white px-5 py-3">
          <div className="min-w-0">
            <div className="truncate text-sm font-bold text-[var(--color-text-main)]">{title}</div>
            <div className="mt-0.5 truncate text-xs text-[var(--color-text-muted)]">{subtitle}</div>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            {footer}
            <button type="button" onClick={onClose} className="rounded-md border border-[var(--color-border)] px-3 py-1.5 text-xs font-semibold text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-hover)]">
              关闭
            </button>
          </div>
        </header>
        <div className="min-h-0 flex-1 overflow-y-auto bg-[#eef3f8] p-5">
          <div className="mx-auto max-w-[1320px] rounded-xl border border-[#d4deea] bg-white p-5 shadow-[var(--shadow-lg)]">
            <QuestionLiveEditor question={question} onChange={onChange} onSave={onSave} saving={saving} />
          </div>
        </div>
      </div>
    </div>
  );
}
