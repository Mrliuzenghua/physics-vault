import { useEffect, useMemo, useState } from 'react';
import { Virtuoso } from 'react-virtuoso';
import type { BasketItem, Question } from '../../types';
import { fetchQuestionsByIds } from '../../services/api';

interface Props {
  open: boolean;
  items: BasketItem[];
  includedQuestionIds: Set<string>;
  onClose: () => void;
  onRemove: (id: string) => void;
  onMove: (id: string, direction: 'up' | 'down') => void;
  onCompose: () => void;
}

function getKnowledge(question: Question): string {
  return question.knowledge_points?.map((point) => point.topic3_name || point.topic2_name || point.topic1_name).find(Boolean)
    || question.knowledge_point
    || '未归类';
}

function comparisonTokens(question: Question): Set<string> {
  const text = (question.canonical_title || question.title || '')
    .replace(/\\[a-zA-Z]+(?:\{[^}]*\})?/g, ' ')
    .replace(/[^\u4e00-\u9fa5a-zA-Z0-9]/g, '')
    .trim()
    .toLowerCase();
  const tokens = new Set<string>();
  for (let index = 0; index < text.length - 1; index += 1) tokens.add(text.slice(index, index + 2));
  if (text.length === 1) tokens.add(text);
  return tokens;
}

function titleSimilarity(left: Question, right: Question): number {
  const leftTokens = comparisonTokens(left);
  const rightTokens = comparisonTokens(right);
  if (!leftTokens.size || !rightTokens.size) return 0;
  const intersection = [...leftTokens].filter((token) => rightTokens.has(token)).length;
  return intersection / new Set([...leftTokens, ...rightTokens]).size;
}

export default function BasketWorkbenchDrawer({ open, items, includedQuestionIds, onClose, onRemove, onMove, onCompose }: Props) {
  const [questions, setQuestions] = useState<Question[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setLoading(true);
    void fetchQuestionsByIds(items.map((item) => item.question_id))
      .then((result) => { if (!cancelled) setQuestions(result); })
      .catch(() => { if (!cancelled) setQuestions([]); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [items, open]);

  const orderedQuestions = useMemo(() => {
    const byId = new Map(questions.map((question) => [question.question_id, question]));
    return items.map((item) => byId.get(item.question_id)).filter((question): question is Question => Boolean(question));
  }, [items, questions]);

  const quality = useMemo(() => {
    const knowledge = new Set(orderedQuestions.map(getKnowledge));
    const sources = new Map<string, number>();
    const difficulties = orderedQuestions.map((question) => Number(question.difficulty || 0)).filter(Boolean);
    orderedQuestions.forEach((question) => {
      const source = question.source || question.primary_paper_id || '未标注来源';
      sources.set(source, (sources.get(source) || 0) + 1);
    });
    const dominant = [...sources.entries()].sort((a, b) => b[1] - a[1])[0];
    const warnings: string[] = [];
    if (orderedQuestions.length >= 6 && knowledge.size < 3) warnings.push('知识点覆盖偏窄，建议补充不同考点。');
    if (dominant && dominant[1] / Math.max(orderedQuestions.length, 1) >= 0.7) warnings.push(`来源“${dominant[0]}”占比偏高。`);
    if (difficulties.length > 2 && Math.max(...difficulties) - Math.min(...difficulties) <= 1) warnings.push('难度梯度较弱，可加入基础或拔高题。');
    if (orderedQuestions.some((question) => !question.answer?.trim())) warnings.push('存在缺少答案的题目。');
    const similarPairs: Array<{ left: Question; right: Question; score: number }> = [];
    orderedQuestions.forEach((question, index) => {
      orderedQuestions.slice(index + 1).forEach((candidate) => {
        const score = titleSimilarity(question, candidate);
        if (score >= 0.55) similarPairs.push({ left: question, right: candidate, score });
      });
    });
    if (similarPairs.length) warnings.unshift(`发现 ${similarPairs.length} 组题干相近的题目，建议确认是否保留。`);
    return {
      knowledgeCount: knowledge.size,
      warnings,
      similarPairs: similarPairs.slice(0, 3),
      isBalanced: warnings.length === 0,
    };
  }, [orderedQuestions]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-40 flex justify-end bg-slate-950/20" role="dialog" aria-modal="true" aria-label="选题篮工作台">
      <section className="flex h-full w-full max-w-xl flex-col bg-[var(--color-bg)] shadow-2xl">
        <header className="flex items-start justify-between border-b border-[var(--color-border)] bg-white px-5 py-4">
          <div><h2 className="text-base font-bold text-[var(--color-text-main)]">选题篮工作台</h2><p className="mt-1 text-xs text-[var(--color-text-muted)]">调整顺序、查看知识点覆盖，并在组卷前完成检查。</p></div>
          <button type="button" onClick={onClose} className="rounded-md px-2 py-1 text-sm text-[var(--color-text-muted)] hover:bg-[var(--color-bg-hover)]">关闭</button>
        </header>
        <div className="grid grid-cols-3 gap-2 border-b border-[var(--color-border)] bg-white px-5 py-3">
          <Metric label="已选题目" value={items.length} />
          <Metric label="覆盖知识点" value={quality.knowledgeCount} />
          <Metric label="已进组卷" value={orderedQuestions.filter((question) => includedQuestionIds.has(question.question_id)).length} />
        </div>
        <div className="mx-5 mt-4 rounded-xl border border-[#cfe2f7] bg-[#f6fbff] px-3 py-2 text-xs leading-5 text-[#426887]">
          <div className="font-semibold">组卷前检查</div>
          {quality.isBalanced ? <div className="mt-1">题目结构基本均衡，可以进入组卷。</div> : <ul className="mt-1 list-disc space-y-0.5 pl-4">{quality.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul>}
        </div>
        <div className="min-h-0 flex-1 overflow-hidden px-5 py-4">
          {quality.similarPairs.length > 0 && <div className="mb-3 rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900"><div className="font-semibold">相近题提醒</div><div className="mt-1 space-y-1">{quality.similarPairs.map(({ left, right, score }) => <div key={`${left.question_id}-${right.question_id}`} className="flex items-center gap-1"><span className="font-medium">{left.question_id}</span><span>与</span><span className="font-medium">{right.question_id}</span><span className="text-amber-700">题干相似度 {Math.round(score * 100)}%</span></div>)}</div></div>}
          {loading ? <div className="py-8 text-center text-sm text-[var(--color-text-muted)]">正在读取选题篮…</div> : orderedQuestions.length === 0 ? <div className="py-8 text-center text-sm text-[var(--color-text-muted)]">选题篮为空</div> : <Virtuoso data={orderedQuestions} className="h-full" increaseViewportBy={{ top: 360, bottom: 680 }} itemContent={(index, question) => <div className="pb-2"><div className="rounded-xl border border-[var(--color-border)] bg-white p-3"><div className="mb-1 flex items-center gap-2 text-xs"><span className="font-bold text-[var(--color-accent)]">{index + 1}</span><span className="font-semibold text-[var(--color-text-secondary)]">{getKnowledge(question)}</span>{includedQuestionIds.has(question.question_id) && <span className="rounded bg-[var(--color-green-light)] px-1.5 py-0.5 text-[10px] font-semibold text-[var(--color-green)]">已进组卷</span>}</div><div className="line-clamp-2 text-sm leading-6 text-[var(--color-text-main)]">{question.canonical_title || question.title || question.question_id}</div><div className="mt-2 flex justify-end gap-1"><button type="button" disabled={index === 0} onClick={() => onMove(question.question_id, 'up')} className="rounded border border-[var(--color-border)] px-2 py-1 text-[11px] disabled:opacity-30">上移</button><button type="button" disabled={index === orderedQuestions.length - 1} onClick={() => onMove(question.question_id, 'down')} className="rounded border border-[var(--color-border)] px-2 py-1 text-[11px] disabled:opacity-30">下移</button><button type="button" onClick={() => onRemove(question.question_id)} className="rounded bg-[var(--color-red-light)] px-2 py-1 text-[11px] text-[var(--color-red)]">移出</button></div></div></div>} />}
        </div>
        <footer className="flex justify-end gap-2 border-t border-[var(--color-border)] bg-white px-5 py-4"><button type="button" onClick={onClose} className="rounded-lg px-3 py-2 text-xs font-semibold text-[var(--color-text-secondary)]">继续选题</button><button type="button" disabled={items.length === 0} onClick={onCompose} className="rounded-lg bg-[var(--color-accent)] px-3 py-2 text-xs font-semibold text-white disabled:opacity-40">进入组卷工作台</button></footer>
      </section>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: number }) {
  return <div className="rounded-lg bg-[var(--color-bg-hover)] px-2 py-2 text-center"><div className="text-lg font-black text-[var(--color-accent)]">{value}</div><div className="text-[10px] text-[var(--color-text-muted)]">{label}</div></div>;
}
