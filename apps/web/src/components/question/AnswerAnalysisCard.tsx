import type { Question } from '../../types';
import LatexRenderer from '../render/LatexRenderer';

interface Props {
  question: Question;
  editMode: boolean;
  form?: Partial<Question>;
  onUpdateField?: (field: string, value: unknown) => void;
  dirtyFields?: Set<string>;
}

export default function AnswerAnalysisCard({
  question,
  editMode,
  form,
  onUpdateField,
  dirtyFields,
}: Props) {
  const data = editMode && form ? form : question;
  const dirty = (f: string) => dirtyFields?.has(f) ?? false;

  const hasAnswer = !!(data.answer && String(data.answer).trim());
  const hasAnalysis = !!(data.analysis && String(data.analysis).trim());

  return (
    <section
      className="mb-5 overflow-hidden rounded-[24px] border"
      style={{
        borderColor: 'rgba(148, 163, 184, 0.18)',
        background: '#ffffff',
        boxShadow: '0 18px 40px rgba(15, 23, 42, 0.06)',
      }}
    >
      <div
        className="flex items-center justify-between border-b px-6 py-4"
        style={{ borderColor: 'rgba(226, 232, 240, 0.9)', background: 'linear-gradient(180deg, #ffffff 0%, #fbfefb 100%)' }}
      >
        <div className="flex items-center gap-3">
          <span
            className="rounded-full px-3 py-1 text-xs font-semibold"
            style={{ background: '#16a34a', color: '#ffffff' }}
          >
            答案与解析
          </span>
          <span className="text-sm font-medium" style={{ color: '#475569' }}>
            独立信息区，更适合教师查看
          </span>
          {dirty('answer') && <span className="inline-block h-2 w-2 rounded-full" style={{ background: '#f59e0b' }} title="答案已修改" />}
          {dirty('analysis') && <span className="inline-block h-2 w-2 rounded-full" style={{ background: '#f59e0b' }} title="解析已修改" />}
        </div>
      </div>

      <div className="grid gap-5 px-6 py-6 lg:grid-cols-[280px_minmax(0,1fr)]">
        <div className="space-y-3">
          <div className="text-xs font-semibold uppercase tracking-[0.18em]" style={{ color: '#94a3b8' }}>
            Answer
          </div>
          {editMode ? (
            <textarea
              value={(form?.answer as string) ?? ''}
              onChange={(e) => onUpdateField?.('answer', e.target.value)}
              rows={6}
              className="w-full rounded-[18px] border px-4 py-3 text-sm leading-7 outline-none"
              style={{
                borderColor: '#dbe5f0',
                background: '#ffffff',
                color: '#0f172a',
                resize: 'vertical',
              }}
            />
          ) : hasAnswer ? (
            <div
              className="rounded-[20px] border px-5 py-5"
              style={{
                borderColor: '#bbf7d0',
                background: 'linear-gradient(180deg, #f6fff7 0%, #ecfdf3 100%)',
              }}
            >
              <div className="mb-2 text-xs font-semibold uppercase tracking-[0.18em]" style={{ color: '#22c55e' }}>
                标准答案
              </div>
              <div className="text-[18px] font-semibold leading-8" style={{ color: '#166534' }}>
                <LatexRenderer text={String(data.answer)} />
              </div>
            </div>
          ) : (
            <div
              className="rounded-[20px] border px-5 py-5 text-sm"
              style={{
                borderColor: '#e2e8f0',
                background: '#f8fafc',
                color: '#94a3b8',
              }}
            >
              暂无答案
            </div>
          )}
        </div>

        <div className="space-y-3">
          <div className="text-xs font-semibold uppercase tracking-[0.18em]" style={{ color: '#94a3b8' }}>
            Analysis
          </div>
          {editMode ? (
            <textarea
              value={(form?.analysis as string) ?? ''}
              onChange={(e) => onUpdateField?.('analysis', e.target.value)}
              rows={12}
              className="w-full rounded-[18px] border px-4 py-3 text-sm leading-7 outline-none"
              style={{
                borderColor: '#dbe5f0',
                background: '#ffffff',
                color: '#0f172a',
                resize: 'vertical',
              }}
            />
          ) : hasAnalysis ? (
            <div
              className="rounded-[20px] border px-5 py-5"
              style={{
                borderColor: '#e2e8f0',
                background: '#fcfdff',
              }}
            >
              <div className="mb-2 text-xs font-semibold uppercase tracking-[0.18em]" style={{ color: '#64748b' }}>
                解题分析
              </div>
              <div className="whitespace-pre-wrap text-[15px] leading-8" style={{ color: '#334155' }}>
                <LatexRenderer text={String(data.analysis)} />
              </div>
            </div>
          ) : (
            <div
              className="rounded-[20px] border px-5 py-5 text-sm"
              style={{
                borderColor: '#e2e8f0',
                background: '#f8fafc',
                color: '#94a3b8',
              }}
            >
              暂无解析
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
