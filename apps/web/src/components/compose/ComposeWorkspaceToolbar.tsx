import type { ReactNode } from 'react';

import { Button } from '../ui/Button';

type OutputProfile = 'student' | 'teacher';
type SaveState = 'idle' | 'saving' | 'saved' | 'error';

interface Props {
  canUndo: boolean;
  canRedo: boolean;
  saveState: SaveState;
  insertMenu: ReactNode;
  outlineOpen: boolean;
  outputProfile: OutputProfile;
  showAnswers: boolean;
  showAnalysis: boolean;
  effectiveZoom: number;
  zoomFitsWidth: boolean;
  inspectorOpen: boolean;
  onUndo: () => void;
  onRedo: () => void;
  onClear: () => void;
  onSave: () => void;
  onOpenHandout: () => void;
  onToggleOutline: () => void;
  onOrganizeByKnowledge: () => void;
  onOpenRules: () => void;
  onFindSupplementCandidates: () => void;
  onBuildTeachingBlueprint: () => void;
  onAutoLayout: () => void;
  onOpenTemplates: () => void;
  onChangeOutputProfile: (profile: OutputProfile) => void;
  onToggleAnswers: () => void;
  onToggleAnalysis: () => void;
  onDecreaseZoom: () => void;
  onResetZoom: () => void;
  onIncreaseZoom: () => void;
  onFitWidth: () => void;
  onToggleInspector: () => void;
  onOpenSlides: () => void;
  onOpenClassroom: () => void;
}

export default function ComposeWorkspaceToolbar({
  canUndo,
  canRedo,
  saveState,
  insertMenu,
  outlineOpen,
  outputProfile,
  showAnswers,
  showAnalysis,
  effectiveZoom,
  zoomFitsWidth,
  inspectorOpen,
  onUndo,
  onRedo,
  onClear,
  onSave,
  onOpenHandout,
  onToggleOutline,
  onOrganizeByKnowledge,
  onOpenRules,
  onFindSupplementCandidates,
  onBuildTeachingBlueprint,
  onAutoLayout,
  onOpenTemplates,
  onChangeOutputProfile,
  onToggleAnswers,
  onToggleAnalysis,
  onDecreaseZoom,
  onResetZoom,
  onIncreaseZoom,
  onFitWidth,
  onToggleInspector,
  onOpenSlides,
  onOpenClassroom,
}: Props) {
  return (
    <>
      <header className="compose-workbench-ui flex h-11 shrink-0 items-center gap-3 border-b border-[#d4deea] bg-white px-4 shadow-[0_1px_3px_rgba(15,23,42,0.04)]">
        <div className="flex h-6 items-center rounded bg-[#2567b8] px-2.5 text-xs font-bold tracking-wide text-white shadow-sm">组卷工作台</div>
        <div className="ml-auto flex shrink-0 items-center gap-1.5">
          <IconButton title="撤销 (Ctrl+Z)" disabled={!canUndo} onClick={onUndo}><UndoIcon /></IconButton>
          <IconButton title="重做 (Ctrl+Y)" disabled={!canRedo} onClick={onRedo}><RedoIcon /></IconButton>
          <ToolDivider />
          <SaveStateDot state={saveState} />
          <Button variant="ghost" size="sm" onClick={onClear}>清空</Button>
          <Button variant="outline" size="sm" onClick={onSave}>保存项目</Button>
          <Button size="sm" onClick={onOpenHandout}>进入讲义排版</Button>
        </div>
      </header>

      <div className="compose-workbench-ui flex h-10 shrink-0 items-center gap-1 overflow-x-auto border-b border-[#d4deea] bg-[#f8fafc] px-3 shadow-[inset_0_-1px_0_rgba(255,255,255,0.55)]">
        <ToolButton active={outlineOpen} onClick={onToggleOutline} title="显示或收起文档大纲">大纲</ToolButton>
        {insertMenu}
        <ToolbarMenu label="智能工具" title="题目补充、规则与自动整理">
          <ToolButton onClick={onOrganizeByKnowledge} title="按题目知识点插入完整讲授卡，可用 Ctrl+Z 撤销">插入知识讲解</ToolButton>
          <ToolButton onClick={onOpenRules} title="设置题数、知识点上限与题型约束">组卷规则</ToolButton>
          <ToolButton onClick={onFindSupplementCandidates} title="按当前规则从题库筛选补题候选，勾选后再加入">自动补题</ToolButton>
          <ToolButton onClick={onBuildTeachingBlueprint} title="按知识点分组、按难度排序，并自动补全章节标题与知识讲解">智能组卷蓝图</ToolButton>
          <ToolButton onClick={onAutoLayout} title="统一题图、清理重复分页并启用智能分页，可用 Ctrl+Z 撤销">自动整理</ToolButton>
        </ToolbarMenu>
        <ToolButton onClick={onOpenTemplates} title="管理并应用组卷模板">模板</ToolButton>
        <ToolDivider />
        <SegmentedControl options={[{ value: 'student', label: '学生版' }, { value: 'teacher', label: '教师版' }]} value={outputProfile} onChange={onChangeOutputProfile} />
        <PillToggle active={showAnswers} onClick={onToggleAnswers}>答案</PillToggle>
        <PillToggle active={showAnalysis} onClick={onToggleAnalysis}>解析</PillToggle>
        <ToolDivider />
        <div className="flex items-center gap-0.5">
          <IconButton title="缩小" onClick={onDecreaseZoom}>−</IconButton>
          <button type="button" onClick={onResetZoom} className="w-12 rounded px-1 py-1 text-center text-xs font-semibold tabular-nums text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-hover)]" title="恢复 100%">{effectiveZoom}%</button>
          <IconButton title="放大" onClick={onIncreaseZoom}>＋</IconButton>
          <ToolButton active={zoomFitsWidth} onClick={onFitWidth}>适应宽度</ToolButton>
        </div>
        <ToolDivider />
        <ToolButton active={inspectorOpen} onClick={onToggleInspector} title="内容显示和组卷预检">内容检查</ToolButton>
        <div className="ml-auto flex items-center gap-1 pl-2">
          <span className="px-1 text-[10px] font-semibold text-[#8295aa]">下一步</span>
          <ToolButton onClick={onOpenHandout}>讲义排版</ToolButton>
          <ToolButton onClick={onOpenSlides}>课件制作</ToolButton>
          <ToolButton onClick={onOpenClassroom}>课堂授课</ToolButton>
        </div>
      </div>
    </>
  );
}

function ToolDivider() { return <div className="mx-1.5 h-5 w-px shrink-0 bg-[#d4deea]" />; }

function ToolbarMenu({ label, title, children }: { label: string; title: string; children: ReactNode }) {
  return <details className="group relative shrink-0"><summary className="flex h-7 cursor-pointer list-none items-center rounded px-2.5 text-xs font-semibold text-[var(--color-text-secondary)] transition-colors hover:bg-white hover:text-[var(--color-text)] hover:shadow-sm" title={title}>{label}<span className="ml-1 text-[10px] transition-transform group-open:rotate-180">▾</span></summary><div className="absolute left-0 top-8 z-40 flex min-w-40 flex-col gap-0.5 rounded-md border border-[#d4deea] bg-white p-1.5 shadow-lg">{children}</div></details>;
}

function ToolButton({ active, children, onClick, title, disabled }: { active?: boolean; children: ReactNode; onClick?: () => void; title?: string; disabled?: boolean }) {
  return <button type="button" onClick={onClick} title={title} disabled={disabled} aria-pressed={active || undefined} className={`h-7 shrink-0 rounded px-2.5 text-xs font-semibold transition-colors ${active ? 'bg-[#e8f1fb] text-[#1f5fb8] shadow-[inset_0_0_0_1px_rgba(37,103,184,0.12)]' : 'text-[var(--color-text-secondary)] hover:bg-white hover:text-[var(--color-text)] hover:shadow-sm'} disabled:cursor-not-allowed disabled:opacity-35`}>{children}</button>;
}

function IconButton({ children, onClick, title, disabled }: { children: ReactNode; onClick?: () => void; title?: string; disabled?: boolean }) {
  return <button type="button" onClick={onClick} title={title} disabled={disabled} aria-label={title} className="flex h-7 w-7 shrink-0 items-center justify-center rounded text-[var(--color-text-secondary)] transition-colors hover:bg-white hover:text-[var(--color-text)] hover:shadow-sm disabled:cursor-not-allowed disabled:opacity-35">{children}</button>;
}

function SegmentedControl({ options, value, onChange }: { options: Array<{ value: OutputProfile; label: string }>; value: OutputProfile; onChange: (value: OutputProfile) => void }) {
  return <div className="flex shrink-0 items-center rounded bg-[#e8eef6] p-0.5 ring-1 ring-[#d7e0eb]">{options.map((option) => <button key={option.value} type="button" onClick={() => onChange(option.value)} className={`h-6 rounded px-2.5 text-xs font-semibold transition-colors ${value === option.value ? 'bg-white text-[#1f5fb8] shadow-sm' : 'text-[var(--color-text-muted)] hover:text-[var(--color-text)]'}`}>{option.label}</button>)}</div>;
}

function PillToggle({ active, children, onClick }: { active: boolean; children: ReactNode; onClick: () => void }) {
  return <button type="button" onClick={onClick} aria-pressed={active} className={`flex h-7 shrink-0 items-center gap-1.5 rounded border px-2.5 text-xs font-semibold transition-colors ${active ? 'border-[#a9c8ef] bg-[#e8f1fb] text-[#1f5fb8]' : 'border-[#d4deea] bg-white/70 text-[var(--color-text-muted)] hover:border-[#bcc9d8] hover:text-[var(--color-text)]'}`}><span className={`h-1.5 w-1.5 rounded-full ${active ? 'bg-[var(--color-accent)]' : 'bg-[var(--color-text-subtle)]'}`} />{children}</button>;
}

function SaveStateDot({ state }: { state: SaveState }) {
  const meta = state === 'saving' ? { label: '保存中…', color: '#3984c6' } : state === 'saved' ? { label: '已保存', color: '#2f9e68' } : state === 'error' ? { label: '保存失败', color: '#c84545' } : { label: '未保存', color: '#94a3b8' };
  return <span className="flex items-center gap-1.5 text-[10px] font-semibold text-[#6e8195]" title={meta.label}><span className={`h-1.5 w-1.5 rounded-full ${state === 'saving' ? 'animate-pulse' : ''}`} style={{ background: meta.color }} />{meta.label}</span>;
}

function UndoIcon() { return <svg className="h-3.5 w-3.5" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6"><path d="M3 7h6a3.5 3.5 0 0 1 0 7H7" strokeLinecap="round" /><path d="M6 3.5L2.5 7 6 10.5" strokeLinecap="round" strokeLinejoin="round" /></svg>; }
function RedoIcon() { return <svg className="h-3.5 w-3.5" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6"><path d="M13 7H7a3.5 3.5 0 0 0 0 7h2" strokeLinecap="round" /><path d="M10 3.5L13.5 7 10 10.5" strokeLinecap="round" strokeLinejoin="round" /></svg>; }
