import type { Question } from '../../types';
import { Button } from '../ui/Button';
import { Dialog } from '../ui/Dialog';
import QuestionCard from './QuestionCard';

interface Props {
  open: boolean;
  onClose: () => void;
  previewQuestions: Question[];
  loading: boolean;
  requestedCount: number;
  actualCount: number;
  totalCandidates: number;
  perSet: number;
  copies: number;
  allowRepeat: boolean;
  excludedIdsText: string;
  conditionSummary: string[];
  onChangePerSet: (value: number) => void;
  onChangeCopies: (value: number) => void;
  onChangeAllowRepeat: (value: boolean) => void;
  onChangeExcludedIdsText: (value: string) => void;
  onStart: () => void;
  onAddAllToBasket: () => void;
  onViewDetail: (id: string) => void;
  onAddToBasket: (id: string) => void;
  inBasketIds: Set<string>;
}

export default function RandomPickModal({
  open,
  onClose,
  previewQuestions,
  loading,
  requestedCount,
  actualCount,
  totalCandidates,
  perSet,
  copies,
  allowRepeat,
  excludedIdsText,
  conditionSummary,
  onChangePerSet,
  onChangeCopies,
  onChangeAllowRepeat,
  onChangeExcludedIdsText,
  onStart,
  onAddAllToBasket,
  onViewDetail,
  onAddToBasket,
  inBasketIds,
}: Props) {
  return (
    <Dialog
      open={open}
      onClose={onClose}
      className="max-w-[1280px] rounded-[24px] border-[#dde6f3] bg-[#fbfdff]"
    >
      <div className="flex items-center justify-between border-b border-[#e7eef8] px-5 py-4">
        <div className="flex items-end gap-3">
          <h2 className="text-[22px] font-bold tracking-tight text-[#2e3d57]">随机选题</h2>
          <div className="pb-0.5 text-lg text-[#8a97aa]">
            请求 <span className="font-semibold text-[#17a977]">{requestedCount}</span>
            <span className="mx-2">/</span>
            实际返回 <span className="font-semibold text-[#416dff]">{actualCount}</span>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="secondary" onClick={onClose}>关闭</Button>
          <Button variant="primary" loading={loading} onClick={onStart}>开始查询</Button>
          <Button variant="outline" onClick={onAddAllToBasket}>加入篮子</Button>
        </div>
      </div>

      <div className="grid h-[78vh] grid-cols-[minmax(0,1fr)_340px] gap-5 px-5 py-5">
        <div className="min-h-0 overflow-y-auto rounded-[22px] border border-[#e3eaf5] bg-white p-4 shadow-[0_10px_24px_rgba(33,56,95,0.05)]">
          {previewQuestions.length > 0 ? (
            <div className="space-y-4">
              {previewQuestions.map((question, index) => (
                <QuestionCard
                  key={`${question.question_id}-${index}`}
                  question={question}
                  index={index + 1}
                  onViewDetail={onViewDetail}
                  onAddToBasket={onAddToBasket}
                  inBasket={inBasketIds.has(question.question_id)}
                />
              ))}
            </div>
          ) : (
            <div className="flex h-full items-center justify-center rounded-[18px] border border-dashed border-[#dce4f1] bg-[#fcfdff] text-[#90a0b6]">
              {loading ? '正在随机抽题...' : '点击“开始查询”生成随机题目预览'}
            </div>
          )}
        </div>

        <div className="min-h-0 overflow-y-auto rounded-[22px] border border-[#e3eaf5] bg-white p-4 shadow-[0_10px_24px_rgba(33,56,95,0.05)]">
          <section className="mb-5">
            <h3 className="text-xl font-bold text-[#394b66]">当前查询条件</h3>
            <p className="mt-2 text-sm text-[#8091a8]">以下筛选条件作为随机选题范围。</p>
            <div className="mt-3 rounded-2xl border border-[#edf2f8] bg-[#fbfdff] px-4 py-4 text-sm text-[#8b98ab]">
              {conditionSummary.length > 0 ? conditionSummary.join('；') : '当前无额外筛选条件。'}
            </div>
            <div className="mt-4 inline-flex rounded-full border border-[#f5dfc8] bg-[#fff8f1] px-4 py-2 text-sm text-[#b97a36]">
              符合条件的题目共 <span className="ml-1 font-semibold text-[#ef7f2d]">{totalCandidates}</span> 道
            </div>
          </section>

          <section className="mb-5">
            <h3 className="text-xl font-bold text-[#394b66]">选取数量</h3>
            <p className="mt-2 text-sm text-[#8091a8]">设置每份抽取题量与生成份数，点击“开始查询”生效。</p>

            <div className="mt-4 rounded-[20px] border border-[#d6e4fb] bg-[#eff6ff] px-5 py-5 text-center">
              <div className="text-[18px] font-bold text-[#2f6fdd]">
                {perSet}<span className="mx-1 text-sm font-medium">道/份</span>
                ×
                <span className="mx-1">{copies}</span><span className="text-sm font-medium">份</span>
                =
                <span className="mx-1">{requestedCount}</span><span className="text-sm font-medium">道</span>
              </div>
              <div className="mt-2 text-sm text-[#6f86aa]">预览区会实时显示当前随机结果</div>
            </div>

            <div className="mt-4 grid grid-cols-2 gap-3">
              <label className="rounded-2xl border border-[#ebf0f7] bg-[#fcfdff] px-4 py-4">
                <div className="mb-2 flex items-center justify-between text-sm font-semibold text-[#536780]">
                  <span>每份数量</span>
                  <span className="text-xs text-[#9ca9bb]">上限 50</span>
                </div>
                <input
                  type="number"
                  min={1}
                  max={50}
                  value={perSet}
                  onChange={(event) => onChangePerSet(Number(event.target.value) || 1)}
                  className="w-full rounded-xl border border-[#e3eaf5] bg-white px-3 py-2 text-center text-xl font-semibold text-[#2d4362] outline-none"
                />
              </label>

              <label className="rounded-2xl border border-[#ebf0f7] bg-[#fcfdff] px-4 py-4">
                <div className="mb-2 flex items-center justify-between text-sm font-semibold text-[#536780]">
                  <span>份数</span>
                  <span className="text-xs text-[#9ca9bb]">上限 20</span>
                </div>
                <input
                  type="number"
                  min={1}
                  max={20}
                  value={copies}
                  onChange={(event) => onChangeCopies(Number(event.target.value) || 1)}
                  className="w-full rounded-xl border border-[#e3eaf5] bg-white px-3 py-2 text-center text-xl font-semibold text-[#2d4362] outline-none"
                />
              </label>
            </div>
          </section>

          <section className="mb-5 rounded-2xl border border-[#ebf0f7] bg-[#fcfdff] px-4 py-4">
            <div className="flex items-center justify-between">
              <div>
                <div className="text-lg font-bold text-[#394b66]">允许重复</div>
                <div className="mt-1 text-sm text-[#8a97aa]">关闭后各份之间不会抽到相同题目</div>
              </div>
              <button
                onClick={() => onChangeAllowRepeat(!allowRepeat)}
                className={`relative h-8 w-14 rounded-full transition-colors ${allowRepeat ? 'bg-[#2f6fdd]' : 'bg-[#d8dee8]'}`}
              >
                <span
                  className={`absolute top-1 h-6 w-6 rounded-full bg-white shadow-sm transition-transform ${allowRepeat ? 'translate-x-7' : 'translate-x-1'}`}
                />
              </button>
            </div>
          </section>

          <section className="rounded-2xl border border-[#ebf0f7] bg-[#fcfdff] px-4 py-4">
            <div className="text-lg font-bold text-[#394b66]">排除题目</div>
            <div className="mt-1 text-sm text-[#8a97aa]">支持按题号排除，每行或每个逗号输入一个题号。</div>
            <textarea
              value={excludedIdsText}
              onChange={(event) => onChangeExcludedIdsText(event.target.value)}
              rows={6}
              placeholder="例如：DEMO-Q-0001"
              className="mt-3 w-full resize-none rounded-2xl border border-[#e3eaf5] bg-white px-3 py-3 text-sm text-[#334863] outline-none"
            />
          </section>
        </div>
      </div>
    </Dialog>
  );
}
