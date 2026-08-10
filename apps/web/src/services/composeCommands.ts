import type { ComposeItem, HandoutTextBlockKind, Question } from '../types';
import { getComposeWorkbenchSnapshot } from '../stores/useComposeWorkbenchStore.ts';

export type ComposeCommand =
  | { type: 'insert_text'; title?: string; content: string; afterId?: string; blockKind?: HandoutTextBlockKind }
  | { type: 'insert_knowledge'; title: string; summary?: string; points?: string[]; afterId?: string }
  | { type: 'insert_page_break'; title?: string; afterId?: string }
  | { type: 'remove_node'; nodeId: string }
  | { type: 'duplicate_node'; nodeId: string; afterId?: string }
  | { type: 'move_node'; nodeId: string; toIndex: number }
  | { type: 'move_node_after'; nodeId: string; afterId?: string }
  | { type: 'update_question'; questionId: string; patch: Partial<Question> }
  | { type: 'update_text'; nodeId: string; patch: { title?: string; content?: string } }
  | { type: 'update_knowledge'; nodeId: string; patch: { title?: string; summary?: string; points?: string[] } }
  | { type: 'update_figure'; questionId: string; figureId: string; displayScale?: number; displayAlign?: 'left' | 'center' | 'right'; caption?: string }
  | { type: 'set_all_figures'; displayScale?: number; displayAlign?: 'left' | 'center' | 'right' };

export interface ComposeCommandBatch {
  composeCommands: ComposeCommand[];
}

function makeId(prefix: string): string {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

function isCommand(value: unknown): value is ComposeCommand {
  if (!value || typeof value !== 'object') return false;
  const command = value as Record<string, unknown>;
  if (command.type === 'insert_text') return typeof command.content === 'string';
  if (command.type === 'insert_knowledge') return typeof command.title === 'string';
  if (command.type === 'insert_page_break') return true;
  if (command.type === 'remove_node') return typeof command.nodeId === 'string';
  if (command.type === 'duplicate_node') return typeof command.nodeId === 'string';
  if (command.type === 'move_node') return typeof command.nodeId === 'string' && Number.isFinite(command.toIndex);
  if (command.type === 'move_node_after') return typeof command.nodeId === 'string';
  if (command.type === 'update_text' || command.type === 'update_knowledge') {
    return typeof command.nodeId === 'string' && Boolean(command.patch) && typeof command.patch === 'object';
  }
  if (command.type === 'update_figure') {
    return typeof command.questionId === 'string' && typeof command.figureId === 'string';
  }
  if (command.type === 'set_all_figures') return Number.isFinite(command.displayScale) || ['left', 'center', 'right'].includes(String(command.displayAlign));
  return command.type === 'update_question'
    && typeof command.questionId === 'string'
    && Boolean(command.patch)
    && typeof command.patch === 'object';
}

function parseCandidate(candidate: string): ComposeCommand[] {
  try {
    const value = JSON.parse(candidate) as Partial<ComposeCommandBatch>;
    return Array.isArray(value.composeCommands) ? value.composeCommands.filter(isCommand) : [];
  } catch {
    return [];
  }
}

export function parseComposeCommandsFromText(text: string): ComposeCommand[] {
  for (const match of text.matchAll(/```(?:json)?\s*([\s\S]*?)```/gi)) {
    const commands = parseCandidate(match[1]);
    if (commands.length > 0) return commands;
  }
  const firstBrace = text.indexOf('{');
  const lastBrace = text.lastIndexOf('}');
  return firstBrace >= 0 && lastBrace > firstBrace
    ? parseCandidate(text.slice(firstBrace, lastBrace + 1))
    : [];
}

export function stripComposeCommandsFromText(text: string): string {
  const withoutFencedBatch = text.replace(/```(?:json)?\s*([\s\S]*?)```/gi, (block, candidate: string) => (
    parseCandidate(candidate).length > 0 ? '' : block
  ));
  const firstBrace = withoutFencedBatch.indexOf('{');
  const lastBrace = withoutFencedBatch.lastIndexOf('}');
  if (firstBrace >= 0 && lastBrace > firstBrace) {
    const candidate = withoutFencedBatch.slice(firstBrace, lastBrace + 1);
    if (parseCandidate(candidate).length > 0) {
      return `${withoutFencedBatch.slice(0, firstBrace)}${withoutFencedBatch.slice(lastBrace + 1)}`.trim();
    }
  }
  return withoutFencedBatch.trim();
}

function insertionIndex(items: ComposeItem[], afterId?: string): number {
  if (!afterId) return items.length;
  const index = items.findIndex((item) => item.id === afterId);
  return index < 0 ? items.length : index + 1;
}

export function applyComposeCommands(items: ComposeItem[], commands: ComposeCommand[]): ComposeItem[] {
  let next = [...items];
  for (const command of commands) {
    if (command.type === 'insert_text') {
      const item: ComposeItem = {
        id: makeId('ai-text'),
        type: 'text',
        title: command.title || '教学说明',
        content: command.content,
        blockKind: command.blockKind || 'body',
      };
      next.splice(insertionIndex(next, command.afterId), 0, item);
    } else if (command.type === 'insert_knowledge') {
      const id = makeId('ai-knowledge');
      const item: ComposeItem = {
        id,
        type: 'knowledge',
        knowledgeId: id,
        title: command.title,
        summary: command.summary || '',
        points: Array.isArray(command.points) ? command.points.map(String) : [],
      };
      next.splice(insertionIndex(next, command.afterId), 0, item);
    } else if (command.type === 'insert_page_break') {
      const item: ComposeItem = { id: makeId('ai-page'), type: 'separator', title: command.title || '分页' };
      next.splice(insertionIndex(next, command.afterId), 0, item);
    } else if (command.type === 'remove_node') {
      next = next.filter((item) => item.id !== command.nodeId);
    } else if (command.type === 'duplicate_node') {
      const source = next.find((item) => item.id === command.nodeId);
      if (!source) continue;
      const duplicate = { ...source, id: makeId(`ai-${source.type}`) } as ComposeItem;
      next.splice(insertionIndex(next, command.afterId || command.nodeId), 0, duplicate);
    } else if (command.type === 'move_node') {
      const fromIndex = next.findIndex((item) => item.id === command.nodeId);
      if (fromIndex < 0) continue;
      const [item] = next.splice(fromIndex, 1);
      const toIndex = Math.max(0, Math.min(Math.trunc(command.toIndex), next.length));
      next.splice(toIndex, 0, item);
    } else if (command.type === 'move_node_after') {
      const fromIndex = next.findIndex((item) => item.id === command.nodeId);
      if (fromIndex < 0) continue;
      const [item] = next.splice(fromIndex, 1);
      next.splice(insertionIndex(next, command.afterId), 0, item);
    } else if (command.type === 'update_question') {
      next = next.map((item) => item.type === 'question' && item.questionId === command.questionId
        ? { ...item, question: item.question ? { ...item.question, ...command.patch, question_id: item.questionId } : item.question }
        : item);
    } else if (command.type === 'update_text') {
      next = next.map((item) => item.id === command.nodeId && item.type === 'text'
        ? { ...item, ...command.patch }
        : item);
    } else if (command.type === 'update_knowledge') {
      next = next.map((item) => item.id === command.nodeId && item.type === 'knowledge'
        ? { ...item, ...command.patch, points: command.patch.points?.map(String) || item.points }
        : item);
    } else if (command.type === 'update_figure') {
      const displayScale = Number.isFinite(command.displayScale)
        ? Math.min(100, Math.max(25, Math.round(command.displayScale!)))
        : undefined;
      next = next.map((item) => item.type === 'question' && item.questionId === command.questionId && item.question
        ? { ...item, question: { ...item.question, figures: (item.question.figures || []).map((figure) => figure.fig_uuid === command.figureId ? { ...figure, display_scale: displayScale ?? figure.display_scale, display_align: command.displayAlign ?? figure.display_align, caption: command.caption ?? figure.caption } : figure) } }
        : item);
    } else if (command.type === 'set_all_figures') {
      const displayScale = Number.isFinite(command.displayScale)
        ? Math.min(100, Math.max(25, Math.round(command.displayScale!)))
        : undefined;
      next = next.map((item) => item.type === 'question' && item.question
        ? { ...item, question: { ...item.question, figures: (item.question.figures || []).map((figure) => ({ ...figure, display_scale: displayScale ?? figure.display_scale, display_align: command.displayAlign ?? figure.display_align })) } }
        : item);
    }
  }
  return next;
}

export function applyComposeCommandsToWorkbench(commands: ComposeCommand[]): number {
  const store = getComposeWorkbenchSnapshot();
  const next = applyComposeCommands(store.items, commands);
  if (next.length === store.items.length && next.every((item, index) => item === store.items[index])) return 0;
  store.commitItems(next);
  return commands.length;
}

export function describeComposeCommand(command: ComposeCommand): string {
  if (command.type === 'insert_text') return `插入文本：${command.title || command.content.slice(0, 24)}`;
  if (command.type === 'insert_knowledge') return `插入知识卡：${command.title}`;
  if (command.type === 'insert_page_break') return '插入分页';
  if (command.type === 'remove_node') return `删除内容：${command.nodeId}`;
  if (command.type === 'duplicate_node') return `复制内容：${command.nodeId}`;
  if (command.type === 'move_node') return `移动内容到第 ${command.toIndex + 1} 位`;
  if (command.type === 'move_node_after') return `移动内容到 ${command.afterId || '文档末尾'} 之后`;
  if (command.type === 'update_text') return `更新文本：${command.nodeId}`;
  if (command.type === 'update_knowledge') return `更新知识卡：${command.nodeId}`;
  if (command.type === 'update_figure') return `调整题图：${command.figureId}`;
  if (command.type === 'set_all_figures') return `统一全部题图${command.displayScale ? `为 ${command.displayScale}%` : ''}${command.displayAlign ? `并${command.displayAlign === 'left' ? '左对齐' : command.displayAlign === 'right' ? '右对齐' : '居中'}` : ''}`;
  return `更新题目：${command.questionId}`;
}
