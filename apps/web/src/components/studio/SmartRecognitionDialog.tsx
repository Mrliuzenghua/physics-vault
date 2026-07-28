import type { RefObject } from 'react';

import LatexRenderer from '../render/LatexRenderer';
import { Dialog } from '../ui/Dialog';
import type { Question as QuestionRecord } from '../../types';

type SmartStatus = 'recognized' | 'retry' | 'pending';

export interface SmartRecognitionSegmentView {
  id: number;
  status: SmartStatus;
  title?: string;
  text: string;
}

interface SmartRecognitionDialogProps {
  open: boolean;
  onClose: () => void;
  sourceName: string;
  sourcePreviewUrl: string;
  loading: boolean;
  refining: boolean;
  error: string | null;
  warnings: string[];
  segments: SmartRecognitionSegmentView[];
  selectedIndex: number;
  selectedQuestion: QuestionRecord | null;
  fileInputRef: RefObject<HTMLInputElement | null>;
  onFileChange: (files: FileList | null) => void | Promise<void>;
  onPickFile: () => void;
  onSelect: (index: number) => void;
  onApplySelected: () => void;
  onRefineSelected: () => void | Promise<void>;
  onRefineAll: () => void | Promise<void>;
  onCopySelected: () => void | Promise<void>;
  onReset: () => void;
  resolveFigureUrl: (path: string) => string;
}

function smartSegmentBorder(status: SmartStatus) {
  if (status === 'recognized') return 'border-[#7ac987] bg-[#f7fcf8]';
  if (status === 'retry') return 'border-[#e8edf4] bg-white';
  return 'border-dashed border-[#f3a63b] bg-white';
}

function smartStatusPill(status: SmartStatus) {
  if (status === 'recognized') return 'bg-[#19b36b] text-white';
  if (status === 'retry') return 'bg-[#ffb028] text-white';
  return 'bg-[#f5f7fb] text-[#7d8ba1]';
}

function smartStatusLabel(status: SmartStatus) {
  if (status === 'recognized') return '已识别';
  if (status === 'retry') return '重试';
  return '待处理';
}

export default function SmartRecognitionDialog({
  open,
  onClose,
  sourceName,
  sourcePreviewUrl,
  loading,
  refining,
  error,
  warnings,
  segments,
  selectedIndex,
  selectedQuestion,
  fileInputRef,
  onFileChange,
  onPickFile,
  onSelect,
  onApplySelected,
  onRefineSelected,
  onRefineAll,
  onCopySelected,
  onReset,
  resolveFigureUrl,
}: SmartRecognitionDialogProps) {
  return (
    <Dialog
      open={open}
      onClose={onClose}
      className="w-[min(96vw,1420px)] max-w-none rounded-[24px] border-[#dbe5f3] bg-white"
    >
      <div className="overflow-hidden rounded-[22px]">
        <div className="flex flex-wrap items-center justify-between gap-4 bg-[linear-gradient(135deg,#31486f,#23365b)] px-5 py-4 text-white">
          <div className="flex min-w-0 flex-wrap items-center gap-6">
            <div className="flex items-center gap-3 whitespace-nowrap">
              <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-[#1b92db]/20 text-xl">🖼</div>
              <div className="text-lg font-semibold">智能识别</div>
            </div>
            <div className="hidden h-7 w-px bg-white/10 lg:block" />
            <div className="max-w-[320px] truncate whitespace-nowrap text-sm text-white/70">
              {sourceName || '支持 Word / PDF / 图片自动识别'}
            </div>
            <div className="whitespace-nowrap rounded-full border border-white/10 bg-white/10 px-4 py-2 text-sm font-semibold">
              共 {segments.length} 个，已识别 {segments.filter((item) => item.status === 'recognized').length} 个
            </div>
          </div>

          <div className="flex flex-wrap items-center justify-end gap-2 text-sm">
            <input
              ref={fileInputRef}
              type="file"
              accept=".doc,.docx,.pdf,.md,.markdown,.txt,.html,.htm,.jpg,.jpeg,.png,.webp"
              className="hidden"
              onChange={(event) => void onFileChange(event.target.files)}
            />
            <button
              onClick={onPickFile}
              disabled={loading || refining}
              className="whitespace-nowrap rounded-xl border border-white/10 bg-white/5 px-4 py-2 text-white/85"
            >
              选择文件
            </button>
            <button
              onClick={onPickFile}
              disabled={loading || refining}
              className="whitespace-nowrap rounded-xl border border-[#c79832] bg-[#6f5622] px-4 py-2 text-[#ffdb7a]"
            >
              {loading ? '识别中...' : '开始识别'}
            </button>
            <button
              onClick={() => void onRefineSelected()}
              disabled={loading || refining || !selectedQuestion}
              className="whitespace-nowrap rounded-xl border border-[#6fd0aa] bg-[#103f46] px-4 py-2 text-[#9ff2ce] disabled:cursor-not-allowed disabled:opacity-50"
            >
              {refining ? 'DeepSeek清洗中...' : '清洗选中'}
            </button>
            <button
              onClick={() => void onRefineAll()}
              disabled={loading || refining || segments.length === 0}
              className="whitespace-nowrap rounded-xl border border-[#6fd0aa] bg-[#103f46] px-4 py-2 text-[#9ff2ce] disabled:cursor-not-allowed disabled:opacity-50"
            >
              清洗全部
            </button>
            <button
              onClick={onApplySelected}
              disabled={refining}
              className="whitespace-nowrap rounded-xl border border-white/10 bg-white/5 px-4 py-2 text-white/85 disabled:cursor-not-allowed disabled:opacity-50"
            >
              导入编辑区
            </button>
            <button
              onClick={() => void onCopySelected()}
              className="whitespace-nowrap rounded-xl border border-white/10 bg-white/5 px-4 py-2 text-white/85"
            >
              复制选中
            </button>
            <button
              onClick={onReset}
              className="whitespace-nowrap rounded-xl border border-white/10 bg-white/5 px-4 py-2 text-white/85"
            >
              清理
            </button>
            <button
              onClick={onClose}
              className="whitespace-nowrap rounded-xl border border-white/10 bg-white/5 px-4 py-2 text-white/85"
            >
              关闭
            </button>
          </div>
        </div>

        <div className="grid h-[78vh] grid-cols-[1.04fr_1.02fr_0.38fr] gap-3 bg-[#f4f6fa] p-3">
          <div className="overflow-hidden rounded-[18px] border border-[#e5eaf1] bg-white">
            <div className="h-full overflow-y-auto bg-[#f4f6fa] p-3">
              <div className="relative rounded-[16px] border border-[#e5eaf1] bg-[#f7f8fb] p-3">
                <div className="absolute right-3 top-3 rounded-[10px] bg-[#f1f3f7] px-3 py-1 text-sm font-semibold text-[#566983]">
                  {selectedIndex + 1}
                </div>
                <div className="mb-3 flex items-center gap-3">
                  <button
                    onClick={onApplySelected}
                    disabled={refining}
                    className="rounded-[12px] bg-[#4aa0ff] px-4 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    导入编辑区
                  </button>
                  <button
                    onClick={() => void onRefineSelected()}
                    disabled={loading || refining || !selectedQuestion}
                    className="rounded-[12px] bg-[#103f46] px-4 py-2 text-sm font-semibold text-[#9ff2ce] disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {refining ? '清洗中...' : 'DeepSeek清洗'}
                  </button>
                  <button
                    onClick={() => void onCopySelected()}
                    className="rounded-[12px] bg-[#f3f5f8] px-4 py-2 text-sm font-semibold text-[#79879c]"
                  >
                    复制内容
                  </button>
                </div>

                <div className="rounded-[14px] bg-white p-5 shadow-inner">
                  <div className="mx-auto max-w-[560px] rounded-[12px] border border-[#eceff5] bg-white px-8 py-8">
                    {sourcePreviewUrl && (
                      <div className="mb-6 overflow-hidden rounded-[12px] border border-[#e5ebf3] bg-[#f8fbff] p-3">
                        <img
                          src={sourcePreviewUrl}
                          alt={sourceName || 'source-preview'}
                          className="mx-auto max-h-[320px] w-full object-contain"
                        />
                      </div>
                    )}

                    {selectedQuestion ? (
                      <div className="space-y-5 text-[#2e3f5c]">
                        <div>
                          <div className="mb-2 text-xs font-semibold tracking-[0.2em] text-[#8ea2bc]">
                            当前识别结果
                          </div>
                          <div className="text-[20px] font-semibold leading-9 text-[#1f2f4c]">
                            <LatexRenderer text={selectedQuestion.title || '未识别到题干'} />
                          </div>
                        </div>

                        {selectedQuestion.options?.length > 0 && (
                          <div className="space-y-3 text-[15px] leading-8">
                            {selectedQuestion.options.map((option) => (
                              <div key={`${selectedQuestion.question_id}-${option.opt}`} className="flex gap-3">
                                <span className="font-semibold text-[#244067]">{option.opt}.</span>
                                <div className="flex-1">
                                  <LatexRenderer text={option.content} />
                                </div>
                              </div>
                            ))}
                          </div>
                        )}

                        {selectedQuestion.figures?.length > 0 && (
                          <div className="space-y-3">
                            {selectedQuestion.figures.map((figure, index) => (
                              <div
                                key={figure.fig_uuid || `${index}`}
                                className="overflow-hidden rounded-[12px] border border-[#e5ebf3] bg-[#f8fbff] p-3"
                              >
                                <img
                                  src={resolveFigureUrl(figure.local_path)}
                                  alt={figure.fig_uuid || `figure-${index + 1}`}
                                  className="mx-auto max-h-[240px] w-full object-contain"
                                />
                              </div>
                            ))}
                          </div>
                        )}

                        <div className="rounded-[12px] bg-[#f7f9fd] px-4 py-3 text-sm leading-7 text-[#6f8097]">
                          <div>题型：{selectedQuestion.question_type || '未识别'}</div>
                          <div>知识点：{selectedQuestion.knowledge_point || '待补充'}</div>
                          <div>答案：{selectedQuestion.answer || '暂无'}</div>
                        </div>
                      </div>
                    ) : (
                      <div className="py-20 text-center text-[#93a3b7]">
                        {loading ? '正在调用后端识别，请稍候...' : '先选择一个文件开始识别'}
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div className="overflow-hidden rounded-[18px] border border-[#e5eaf1] bg-white">
            <div className="h-full overflow-y-auto bg-[#f4f6fa] p-3">
              {error && (
                <div className="mb-3 rounded-[14px] border border-[#ffd5c7] bg-[#fff7f4] px-4 py-3 text-sm text-[#d4582d]">
                  {error}
                </div>
              )}
              {warnings.length > 0 && (
                <div className="mb-3 rounded-[14px] border border-[#f4dfac] bg-[#fffaf0] px-4 py-3 text-sm text-[#9c6b12]">
                  {warnings[0]}
                </div>
              )}
              {refining && (
                <div className="mb-3 rounded-[14px] border border-[#a8d8ff] bg-[#eef7ff] px-4 py-3 text-sm font-semibold text-[#2c6fa7]">
                  正在调用 DeepSeek 清洗切片结果，请稍等...
                </div>
              )}
              <div className="space-y-3">
                {segments.length === 0 && !loading && (
                  <div className="rounded-[16px] border border-dashed border-[#d8e1ef] bg-white px-5 py-8 text-center text-[#95a3b7]">
                    选择文件后，这里会显示逐题识别结果。
                  </div>
                )}

                {loading && segments.length === 0 && (
                  <div className="rounded-[16px] border border-[#e8edf4] bg-white px-5 py-8 text-center text-[#6f8199]">
                    正在创建批次并调用识别服务...
                  </div>
                )}

                {segments.map((segment, index) => (
                  <button
                    type="button"
                    key={segment.id}
                    onClick={() => onSelect(index)}
                    className={`relative block min-h-[150px] w-full rounded-[16px] border p-5 text-left transition ${smartSegmentBorder(segment.status)} ${
                      index === selectedIndex ? 'ring-2 ring-[#7aa8ff]' : ''
                    }`}
                  >
                    <div className="mb-3 pr-16 text-sm font-semibold text-[#6e80a0]">{segment.title || `第 ${segment.id} 题`}</div>
                    <div className={`pr-16 text-[16px] leading-8 [word-break:break-word] ${segment.status === 'recognized' ? 'text-[#234067]' : 'text-[#e95321]'}`}>
                      {segment.text}
                    </div>
                    <div className="absolute bottom-3 right-3 rounded-[10px] bg-[#f1f3f7] px-3 py-1 text-sm font-semibold text-[#566983]">
                      {segment.id}
                    </div>
                  </button>
                ))}
              </div>
            </div>
          </div>

          <div className="overflow-hidden rounded-[18px] border border-[#e5eaf1] bg-[#eef1f5]">
            <div className="h-full overflow-y-auto p-3">
              <div className="space-y-3">
                {segments.map((segment, index) => (
                  <div
                    key={`nav-${segment.id}`}
                    className={`rounded-[14px] border px-3 py-4 ${
                      index === selectedIndex ? 'border-[#7aa8ff] bg-[#f7fbff]' : 'border-[#e7ebf2] bg-white'
                    }`}
                  >
                    <button type="button" onClick={() => onSelect(index)} className="flex w-full flex-col gap-2 text-left">
                      <span className="text-[18px] font-semibold text-[#425572]">{segment.id}</span>
                      <span className={`inline-flex w-fit whitespace-nowrap rounded-[12px] px-3 py-1 text-sm font-semibold ${smartStatusPill(segment.status)}`}>
                        {smartStatusLabel(segment.status)}
                      </span>
                    </button>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>
    </Dialog>
  );
}
