import { useCallback, useEffect, useMemo, useState } from 'react';
import { ArrowLeft, ArrowRight, CheckCircle2, RefreshCw, ShieldCheck, TriangleAlert } from 'lucide-react';
import { Link } from 'react-router-dom';

import {
  fetchMissingKnowledgeDiagnosis,
  type MissingKnowledgeDiagnosisItem,
} from '../services/catalogApi';
import {
  confirmQuestionKnowledgeReplacement,
  previewQuestionKnowledgeReplacement,
  type KnowledgeReplacementPreview,
} from '../services/metadataApi';

const PAGE_SIZE = 10;

export default function CatalogMaintenancePage() {
  const [items, setItems] = useState<MissingKnowledgeDiagnosisItem[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<Record<string, string>>({});
  const [previews, setPreviews] = useState<Record<string, KnowledgeReplacementPreview>>({});
  const [actionId, setActionId] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetchMissingKnowledgeDiagnosis(PAGE_SIZE, offset);
      setItems(response.items);
      setTotal(response.total);
      setSelected((current) => {
        const next = { ...current };
        for (const item of response.items) {
          next[item.question_id] ||= item.recommended_topic3_ids[0] || item.suggestions[0]?.topic3_id || '';
        }
        return next;
      });
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : '读取未归类题失败');
    } finally {
      setLoading(false);
    }
  }, [offset]);

  useEffect(() => { void load(); }, [load]);

  const page = Math.floor(offset / PAGE_SIZE) + 1;
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const reliableCount = useMemo(() => items.filter(isReliableCandidate).length, [items]);

  const preview = async (item: MissingKnowledgeDiagnosisItem) => {
    const topic3Id = selected[item.question_id];
    const suggestion = item.suggestions.find((candidate) => candidate.topic3_id === topic3Id);
    if (!topic3Id || !suggestion) return;
    setActionId(item.question_id);
    setNotice(null);
    try {
      const result = await previewQuestionKnowledgeReplacement(
        item.question_id,
        topic3Id,
        Math.max(0, Math.min(1, suggestion.score / 100)),
      );
      setPreviews((current) => ({ ...current, [item.question_id]: result }));
    } catch (requestError) {
      setNotice(requestError instanceof Error ? requestError.message : '生成确认预览失败');
    } finally {
      setActionId(null);
    }
  };

  const confirm = async (item: MissingKnowledgeDiagnosisItem) => {
    const plan = previews[item.question_id];
    const operationId = plan?.operation_plan?.operation_id;
    if (!operationId) return;
    setActionId(item.question_id);
    setNotice(null);
    try {
      const result = await confirmQuestionKnowledgeReplacement(operationId);
      if (result.status !== 'completed') throw new Error(result.error || `操作状态：${result.status}`);
      setItems((current) => current.filter((candidate) => candidate.question_id !== item.question_id));
      setTotal((current) => Math.max(0, current - 1));
      setNotice(`已确认 ${item.question_id} 的知识目录${result.result?.audit_batch_id ? `，审计批次 ${result.result.audit_batch_id}` : ''}`);
    } catch (requestError) {
      setNotice(requestError instanceof Error ? requestError.message : '确认知识目录失败');
    } finally {
      setActionId(null);
    }
  };

  return (
    <div className="mx-auto w-full max-w-6xl px-4 py-5 lg:px-6">
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <ShieldCheck size={20} className="text-[#1768c5]" />
            <h1 className="text-xl font-bold text-[#263b52]">知识目录维护</h1>
          </div>
          <p className="mt-1 text-sm text-[#718196]">逐题查看推荐依据；只有点击预览并再次确认后，才会写入正式题库。</p>
        </div>
        <button type="button" onClick={() => void load()} disabled={loading} className="inline-flex items-center gap-1.5 rounded-md border border-[#dce3ec] bg-white px-3 py-2 text-xs font-semibold text-[#52657a] hover:bg-[#f5f8fb] disabled:opacity-60">
          <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />刷新
        </button>
      </div>

      <div className="mb-4 grid gap-3 sm:grid-cols-3">
        <Summary label="未归类题" value={total} tone="warning" />
        <Summary label="本页可靠候选" value={reliableCount} tone="success" />
        <Summary label="本页需重点判断" value={Math.max(0, items.length - reliableCount)} />
      </div>

      {notice && <div className="mb-4 rounded-md border border-[#cfe0f4] bg-[#f1f7ff] px-3 py-2 text-sm text-[#285d91]">{notice}</div>}
      {error && <div className="rounded-md border border-[#efc9c9] bg-[#fff4f4] px-3 py-3 text-sm text-[#a33b3b]">{error}</div>}
      {loading && <div className="rounded-lg border border-[#e1e7ee] bg-white py-16 text-center text-sm text-[#718196]">正在分析题干与知识目录…</div>}

      {!loading && !error && items.length === 0 && (
        <div className="rounded-lg border border-[#d8eadf] bg-[#f5fbf7] py-16 text-center">
          <CheckCircle2 size={34} className="mx-auto text-[#3e8a61]" />
          <div className="mt-3 font-semibold text-[#2d6348]">当前页没有待处理题目</div>
        </div>
      )}

      <div className="space-y-3">
        {items.map((item) => {
          const plan = previews[item.question_id];
          const selectedId = selected[item.question_id] || '';
          const reliable = isReliableCandidate(item);
          const contentIssue = item.content_quality?.status !== undefined && item.content_quality.status !== 'ok';
          return (
            <article key={item.question_id} className="rounded-lg border border-[#dce3ec] bg-white p-4 shadow-sm">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className={`rounded px-2 py-0.5 text-[11px] font-bold ${reliable ? 'bg-[#eef9f2] text-[#28764b]' : contentIssue ? 'bg-[#fff0f0] text-[#a33b3b]' : 'bg-[#fff7e8] text-[#a35b0a]'}`}>
                      {reliable ? '可靠候选' : contentIssue ? contentIssueLabel(item) : '需要人工判断'}
                    </span>
                    <Link to={`/browse?query=${encodeURIComponent(item.question_id)}&search_mode=strict`} className="text-xs font-semibold text-[#1768c5] hover:underline">查看原题</Link>
                  </div>
                  <h2 className="mt-2 text-sm font-semibold leading-6 text-[#2d4258]">{item.title_preview || item.question_id}</h2>
                  <div className="mt-1 font-mono text-[11px] text-[#8a98a8]">{item.question_id}</div>
                </div>
                <div className="rounded-md bg-[#f7f9fb] px-3 py-2 text-right text-[11px] text-[#718196]">
                  <div>最高分 <b className="text-[#344a61]">{item.auto_fix_evidence.top_score}</b></div>
                  <div>领先第二候选 {item.auto_fix_evidence.score_margin}</div>
                </div>
              </div>

              {contentIssue && (
                <div className="mt-3 rounded-md border border-[#efc9c9] bg-[#fff6f6] px-3 py-3 text-xs leading-5 text-[#934343]">
                  <div className="font-bold">{item.content_quality?.message}</div>
                  {item.content_quality?.issues.map((issue) => <div key={issue}>· {issue}</div>)}
                </div>
              )}

              {item.suggestions.length > 0 ? (
                <div className="mt-4 grid gap-2 lg:grid-cols-3">
                  {item.suggestions.map((suggestion) => (
                    <label key={suggestion.topic3_id} className={`cursor-pointer rounded-md border p-3 ${selectedId === suggestion.topic3_id ? 'border-[#4f8fd3] bg-[#f2f7fd]' : 'border-[#e2e7ed] hover:bg-[#fafbfd]'}`}>
                      <div className="flex items-start gap-2">
                        <input type="radio" name={`knowledge-${item.question_id}`} checked={selectedId === suggestion.topic3_id} onChange={() => {
                          setSelected((current) => ({ ...current, [item.question_id]: suggestion.topic3_id }));
                          setPreviews((current) => {
                            const next = { ...current };
                            delete next[item.question_id];
                            return next;
                          });
                        }} className="mt-1" />
                        <div className="min-w-0">
                          <div className="text-sm font-bold text-[#344a61]">{suggestion.topic3_name}</div>
                          <div className="mt-0.5 text-[11px] text-[#8290a0]">{suggestion.topic1_name} / {suggestion.topic2_name}</div>
                          <div className="mt-2 text-xs leading-5 text-[#65768a]">{suggestion.rationale}</div>
                          <div className="mt-2 text-[11px] font-semibold text-[#52779c]">{evidenceSourceLabel(suggestion.evidence_source)} · 匹配分 {suggestion.score} · {suggestion.confidence}</div>
                        </div>
                      </div>
                    </label>
                  ))}
                </div>
              ) : (
                <div className="mt-4 flex items-center gap-2 rounded-md bg-[#fff8ed] px-3 py-3 text-xs text-[#9a641c]"><TriangleAlert size={15} />暂无可靠候选，请先查看原题并补充目录。</div>
              )}

              {plan && (
                <div className="mt-3 rounded-md border border-[#cfe0f4] bg-[#f5f9ff] px-3 py-3 text-xs text-[#45627e]">
                  <b>确认预览：</b>原知识点 {plan.before_links.length} 个，将替换为所选候选。预览已绑定当前题目版本，题目变化后会拒绝执行。
                </div>
              )}

              <div className="mt-4 flex justify-end gap-2">
                {contentIssue ? (
                  <span className="rounded-md bg-[#f5f7fa] px-3 py-2 text-xs font-semibold text-[#718196]">请先通过“查看原题”修复内容，再刷新诊断</span>
                ) : !plan ? (
                  <button type="button" disabled={!selectedId || actionId === item.question_id} onClick={() => void preview(item)} className="rounded-md bg-[#1768c5] px-3 py-2 text-xs font-bold text-white disabled:opacity-50">预览修改</button>
                ) : (
                  <>
                    <button type="button" onClick={() => setPreviews((current) => {
                      const next = { ...current };
                      delete next[item.question_id];
                      return next;
                    })} className="rounded-md border border-[#d9e0e8] px-3 py-2 text-xs font-semibold text-[#607286]">返回选择</button>
                    <button type="button" disabled={actionId === item.question_id || !plan.requires_confirmation} onClick={() => void confirm(item)} className="rounded-md bg-[#28764b] px-3 py-2 text-xs font-bold text-white disabled:opacity-50">确认写入正式题库</button>
                  </>
                )}
              </div>
            </article>
          );
        })}
      </div>

      <div className="mt-5 flex items-center justify-between border-t border-[#e3e8ee] pt-4 text-xs text-[#718196]">
        <button type="button" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))} className="inline-flex items-center gap-1 rounded-md border border-[#dce3ec] bg-white px-3 py-2 font-semibold disabled:opacity-40"><ArrowLeft size={13} />上一页</button>
        <span>第 {page} / {pages} 页</span>
        <button type="button" disabled={page >= pages} onClick={() => setOffset(offset + PAGE_SIZE)} className="inline-flex items-center gap-1 rounded-md border border-[#dce3ec] bg-white px-3 py-2 font-semibold disabled:opacity-40">下一页<ArrowRight size={13} /></button>
      </div>
    </div>
  );
}

function isReliableCandidate(item: MissingKnowledgeDiagnosisItem): boolean {
  return item.content_quality?.status !== 'content_fragment'
    && item.content_quality?.status !== 'suspected_cross_subject'
    && item.suggestions.length > 0
    && item.auto_fix_evidence.top_score >= 80
    && item.auto_fix_evidence.score_margin >= 15;
}

function contentIssueLabel(item: MissingKnowledgeDiagnosisItem): string {
  if (item.content_quality?.status === 'suspected_cross_subject') return '疑似跨学科';
  if (item.content_quality?.requires_image_review) return '需回看原图';
  return '正文残缺';
}

function evidenceSourceLabel(source: string | undefined): string {
  return ({ prompt: '题干证据', options: '选项证据', figure: '图片说明', analysis: '解析辅助证据' } as Record<string, string>)[source || ''] || '文本证据';
}

function Summary({ label, value, tone }: { label: string; value: number; tone?: 'warning' | 'success' }) {
  const classes = tone === 'warning' ? 'bg-[#fff8ed] text-[#9a641c]' : tone === 'success' ? 'bg-[#f1f9f4] text-[#28764b]' : 'bg-[#f5f7fa] text-[#52657a]';
  return <div className={`rounded-lg px-4 py-3 ${classes}`}><div className="text-xs font-semibold">{label}</div><div className="mt-1 text-2xl font-black tabular-nums">{value}</div></div>;
}
