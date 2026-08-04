import type { JSONContent } from '@tiptap/core';
import Placeholder from '@tiptap/extension-placeholder';
import { EditorContent, useEditor } from '@tiptap/react';
import StarterKit from '@tiptap/starter-kit';
import {
  Bold,
  Eraser,
  Heading2,
  ImagePlus,
  Italic,
  List,
  ListOrdered,
  Quote,
  Redo2,
  Sigma,
  Table2,
  Undo2,
} from 'lucide-react';
import { useEffect, useRef, useState, type ReactNode } from 'react';
import { QUESTION_EDITOR_NODES, figureNode, formulaNode } from './questionEditorNodes';
import { imageFileUrl } from '../../utils/imageUrl';
import { RICH_CONTENT_NODES, richImageNode, richTableNode } from './RichContentNodes';

export interface FigureAsset {
  fig_uuid: string;
  local_path: string;
  display_scale?: number | null;
  display_align?: 'left' | 'center' | 'right' | null;
}

export interface FigureInsertRequest {
  requestId: number;
  figure: FigureAsset;
}

interface StructuredTextEditorProps {
  value: string;
  onChange: (value: string) => void;
  document?: Record<string, unknown>;
  onDocumentChange?: (document: JSONContent) => void;
  figures?: FigureAsset[];
  onFigureScaleChange?: (figureId: string, displayScale: number) => void;
  onFigureAlignChange?: (figureId: string, displayAlign: 'left' | 'center' | 'right') => void;
  storageKey?: string;
  placeholder?: string;
  minHeight?: number;
  compact?: boolean;
  showToolbar?: boolean;
  insertFigureRequest?: FigureInsertRequest | null;
  onRequestImage?: () => void;
}

function escapeHtml(value: string): string {
  return value
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;');
}

function inlineTextToHtml(value: string, figuresById: Map<string, FigureAsset>): string {
  return escapeHtml(value).split(/(!\[fig:[^\]]+\]|!\[[^\]]*\]\((?:data:image\/[^)\n]+|\/files\/[^)\n]+)\)|\$\$?[^$\n]+\$\$?)/g).map((part) => {
    const figure = part.match(/^!\[fig:([^\]]+)\]$/);
    if (figure) {
      const asset = figuresById.get(figure[1]);
      const src = imageFileUrl(asset?.local_path) || '';
      const scale = Math.min(100, Math.max(25, Number(asset?.display_scale ?? 60)));
      const align = asset?.display_align || 'center';
      return `<span data-question-figure="${escapeHtml(figure[1])}" data-question-figure-src="${escapeHtml(src)}" data-question-figure-scale="${scale}" data-question-figure-align="${align}">图 ${escapeHtml(figure[1])}</span>`;
    }
    const image = part.match(/^!\[([^\]]*)\]\(([^)\n]+)\)$/);
    if (image) return `<img data-rich-image="true" src="${escapeHtml(image[2])}" alt="${escapeHtml(image[1])}" />`;
    const formula = part.match(/^\$\$?([^$\n]+)\$\$?$/);
    if (formula) {
      return `<span data-question-formula="${escapeHtml(formula[1])}">$${escapeHtml(formula[1])}$</span>`;
    }
    return part
      .replace(/`([^`\n]+)`/g, '<code>$1</code>')
      .replace(/\*\*([^*\n]+)\*\*/g, '<strong>$1</strong>')
      .replace(/~~([^~\n]+)~~/g, '<s>$1</s>')
      .replace(/(^|[^*])\*([^*\n]+)\*(?!\*)/g, '$1<em>$2</em>');
  }).join('');
}

function textToHtml(value: string, figures: FigureAsset[] = []): string {
  const figuresById = new Map(figures.map((figure) => [figure.fig_uuid, figure]));
  const lines = value.replace(/\r\n?/g, '\n').split('\n');
  const blocks: string[] = [];

  for (let index = 0; index < lines.length;) {
    const line = lines[index];
    const nextLine = lines[index + 1] || '';
    if (looksLikeMarkdownTableRow(line) && looksLikeMarkdownTableSeparator(nextLine)) {
      const rows = [parseMarkdownTableRow(line)];
      index += 2;
      while (index < lines.length && looksLikeMarkdownTableRow(lines[index])) {
        rows.push(parseMarkdownTableRow(lines[index]));
        index += 1;
      }
      const width = Math.max(...rows.map((row) => row.length), 2);
      const normalized = [rows[0], ...rows.slice(1)].map((row) => Array.from({ length: width }, (_, cellIndex) => row[cellIndex] || ''));
      blocks.push(`<div data-rich-table="${escapeHtml(encodeURIComponent(JSON.stringify(normalized)))}"></div>`);
      continue;
    }
    const bulletMatch = line.match(/^\s*[-*+]\s+(.+)$/);
    const orderedMatch = line.match(/^\s*\d+[.)]\s+(.+)$/);

    if (bulletMatch) {
      const items: string[] = [];
      while (index < lines.length) {
        const match = lines[index].match(/^\s*[-*+]\s+(.+)$/);
        if (!match) break;
        items.push(`<li><p>${inlineTextToHtml(match[1], figuresById)}</p></li>`);
        index += 1;
      }
      blocks.push(`<ul>${items.join('')}</ul>`);
      continue;
    }

    if (orderedMatch) {
      const items: string[] = [];
      while (index < lines.length) {
        const match = lines[index].match(/^\s*\d+[.)]\s+(.+)$/);
        if (!match) break;
        items.push(`<li><p>${inlineTextToHtml(match[1], figuresById)}</p></li>`);
        index += 1;
      }
      blocks.push(`<ol>${items.join('')}</ol>`);
      continue;
    }

    const heading = line.match(/^(#{1,3})\s+(.+)$/);
    if (heading) {
      const level = Math.min(3, heading[1].length);
      blocks.push(`<h${level}>${inlineTextToHtml(heading[2], figuresById)}</h${level}>`);
    } else if (/^>\s?/.test(line)) {
      blocks.push(`<blockquote><p>${inlineTextToHtml(line.replace(/^>\s?/, ''), figuresById)}</p></blockquote>`);
    } else {
      blocks.push(`<p>${inlineTextToHtml(line, figuresById)}</p>`);
    }
    index += 1;
  }

  return blocks.join('') || '<p></p>';
}

function looksLikeMarkdownTableRow(line: string): boolean {
  return line.includes('|') && line.split('|').filter((cell) => cell.trim()).length >= 2;
}

function looksLikeMarkdownTableSeparator(line: string): boolean {
  const cells = line.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map((cell) => cell.trim());
  return cells.length >= 2 && cells.every((cell) => /^:?-{3,}:?$/.test(cell));
}

function parseMarkdownTableRow(line: string): string[] {
  return line.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map((cell) => cell.trim());
}

function serializeInline(node: JSONContent): string {
  if (node.type === 'questionFigure') return `![fig:${String(node.attrs?.figureId || '')}]`;
  if (node.type === 'questionFormula') return `$${String(node.attrs?.latex || '')}$`;
  if (node.type === 'hardBreak') return '\n';
  let value = node.text || (node.content || []).map(serializeInline).join('');
  for (const mark of node.marks || []) {
    if (mark.type === 'bold') value = `**${value}**`;
    if (mark.type === 'italic') value = `*${value}*`;
    if (mark.type === 'strike') value = `~~${value}~~`;
    if (mark.type === 'code') value = `\`${value}\``;
  }
  return value;
}

function serializeBlock(node: JSONContent): string {
  const children = node.content || [];
  if (node.type === 'paragraph') return children.map(serializeInline).join('');
  if (node.type === 'heading') return `${'#'.repeat(Math.min(3, Math.max(1, Number(node.attrs?.level || 2))))} ${children.map(serializeInline).join('')}`;
  if (node.type === 'blockquote') return children.map(serializeBlock).join('\n').split('\n').map((line) => `> ${line}`).join('\n');
  if (node.type === 'bulletList') return children.map((child) => `- ${serializeBlock(child)}`).join('\n');
  if (node.type === 'orderedList') return children.map((child, index) => `${index + 1}. ${serializeBlock(child)}`).join('\n');
  if (node.type === 'listItem') return children.map(serializeBlock).join('\n');
  if (node.type === 'codeBlock') return `\`\`\`\n${children.map(serializeInline).join('')}\n\`\`\``;
  if (node.type === 'horizontalRule') return '---';
  if (node.type === 'richImage') return `![${String(node.attrs?.alt || '知识点图片')}](${String(node.attrs?.src || '')})`;
  if (node.type === 'richTable') {
    const cells = Array.isArray(node.attrs?.cells) ? node.attrs.cells.map((row) => Array.isArray(row) ? row.map((cell) => String(cell ?? '')) : []) : [];
    if (cells.length < 2 || cells[0].length < 2) return '';
    const row = (items: string[]) => `| ${items.map((item) => item.replace(/\|/g, '\\|')).join(' | ')} |`;
    return [row(cells[0]), row(cells[0].map(() => '---')), ...cells.slice(1).map(row)].join('\n');
  }
  return children.map(serializeBlock).join('\n');
}

function editorText(document: JSONContent): string {
  return (document.content || []).map(serializeBlock).join('\n').replace(/\n{3,}/g, '\n\n').trimEnd();
}

function loadStoredDocument(storageKey?: string): JSONContent | null {
  if (!storageKey) return null;
  try {
    const raw = localStorage.getItem(storageKey);
    if (!raw) return null;
    const parsed: unknown = JSON.parse(raw);
    return parsed && typeof parsed === 'object' ? parsed as JSONContent : null;
  } catch {
    return null;
  }
}

function saveStoredDocument(storageKey: string | undefined, document: JSONContent) {
  if (!storageKey) return;
  try {
    localStorage.setItem(storageKey, JSON.stringify(document));
  } catch {
    // Local persistence is an enhancement; server saving remains authoritative.
  }
}

function hydrateFigureNodes(document: JSONContent, figures: FigureAsset[]): JSONContent {
  const figuresById = new Map(figures.map((figure) => [figure.fig_uuid, figure]));
  const hydrate = (node: JSONContent): JSONContent => {
    const content = node.content?.map((child) => hydrate(child as JSONContent));
    if (node.type !== 'questionFigure') return { ...node, ...(content ? { content } : {}) };
    const figure = figuresById.get(String(node.attrs?.figureId || ''));
    if (!figure) return { ...node, ...(content ? { content } : {}) };
    return {
      ...node,
      ...(content ? { content } : {}),
      attrs: {
        ...node.attrs,
        src: imageFileUrl(figure.local_path) || '',
        displayScale: Number(node.attrs?.displayScale ?? figure.display_scale ?? 60),
        displayAlign: String(node.attrs?.displayAlign ?? figure.display_align ?? 'center'),
      },
    };
  };
  return hydrate(document);
}

export default function StructuredTextEditor({
  value,
  onChange,
  document,
  onDocumentChange,
  figures = [],
  onFigureScaleChange,
  onFigureAlignChange,
  storageKey,
  placeholder = '输入内容',
  minHeight = 112,
  compact = false,
  showToolbar = true,
  insertFigureRequest = null,
  onRequestImage,
}: StructuredTextEditorProps) {
  const [, refreshToolbar] = useState(0);
  const [slashMenuOpen, setSlashMenuOpen] = useState(false);
  const reportedFigureScales = useRef(new Map<string, number>());
  const reportedFigureAlignments = useRef(new Map<string, string>());
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const insertedRequestRef = useRef(0);
  const storedDocument = loadStoredDocument(storageKey);
  const suppliedDocument = document as JSONContent | undefined;
  const initialDocument = suppliedDocument && editorText(suppliedDocument) === value
    ? hydrateFigureNodes(suppliedDocument, figures)
    : storedDocument && editorText(storedDocument) === value
      ? hydrateFigureNodes(storedDocument, figures)
      : null;
  const editor = useEditor({
    extensions: [StarterKit.configure({ heading: { levels: [2, 3] } }), ...QUESTION_EDITOR_NODES, ...RICH_CONTENT_NODES, Placeholder.configure({ placeholder })],
    content: initialDocument || textToHtml(value, figures),
    editorProps: { attributes: { class: 'pv-tiptap-content', 'aria-label': placeholder } },
    onUpdate: ({ editor: currentEditor }) => {
      const document = currentEditor.getJSON();
      const currentBlockText = currentEditor.state.selection.$from.parent.textContent.trim();
      setSlashMenuOpen(currentBlockText.startsWith('/'));
      onChange(editorText(document));
      const reportFigureLayout = (figure: JSONContent) => {
        if (figure.type === 'questionFigure') {
          const figureId = String(figure.attrs?.figureId || '');
          const displayScale = Number(figure.attrs?.displayScale ?? 60);
          const displayAlign = (['left', 'center', 'right'].includes(String(figure.attrs?.displayAlign)) ? figure.attrs?.displayAlign : 'center') as 'left' | 'center' | 'right';
          if (figureId && reportedFigureScales.current.get(figureId) !== displayScale) {
            reportedFigureScales.current.set(figureId, displayScale);
            onFigureScaleChange?.(figureId, displayScale);
          }
          if (figureId && reportedFigureAlignments.current.get(figureId) !== displayAlign) {
            reportedFigureAlignments.current.set(figureId, displayAlign);
            onFigureAlignChange?.(figureId, displayAlign);
          }
        }
        for (const child of figure.content || []) reportFigureLayout(child as JSONContent);
      };
      reportFigureLayout(document);
      onDocumentChange?.(document);
      saveStoredDocument(storageKey, document);
    },
    onTransaction: () => refreshToolbar((current) => current + 1),
  });

  useEffect(() => {
    if (!editor) return;
    const frame = window.requestAnimationFrame(() => {
      const currentDocument = editor.getJSON();
      const currentValue = editorText(currentDocument);
      if (suppliedDocument && editorText(suppliedDocument) === value) {
        const hydrated = hydrateFigureNodes(suppliedDocument, figures);
        if (JSON.stringify(currentDocument) !== JSON.stringify(hydrated)) {
          editor.commands.setContent(hydrated, { emitUpdate: false });
        }
      } else if (currentValue !== value) {
        editor.commands.setContent(textToHtml(value, figures), { emitUpdate: false });
      }
    });
    return () => window.cancelAnimationFrame(frame);
  }, [editor, figures, suppliedDocument, value]);

  useEffect(() => {
    if (!editor || !insertFigureRequest || insertedRequestRef.current === insertFigureRequest.requestId) return;
    insertedRequestRef.current = insertFigureRequest.requestId;
    const figure = insertFigureRequest.figure;
    editor.chain().focus().insertContent(figureNode(
      figure.fig_uuid,
      imageFileUrl(figure.local_path) || '',
      Number(figure.display_scale ?? 60),
      figure.display_align || 'center',
    )).run();
  }, [editor, insertFigureRequest]);

  if (!editor) return null;

  const insertImage = (file: File) => {
    if (!file.type.startsWith('image/')) return;
    const reader = new FileReader();
    reader.onload = () => {
      const src = typeof reader.result === 'string' ? reader.result : '';
      if (src) editor.chain().focus().insertContent(richImageNode(src, file.name)).run();
    };
    reader.readAsDataURL(file);
  };

  const runSlashCommand = (command: 'heading' | 'formula' | 'table' | 'image') => {
    const { $from } = editor.state.selection;
    editor.chain().focus().deleteRange({ from: $from.start(), to: $from.pos }).run();
    if (command === 'heading') editor.chain().focus().toggleHeading({ level: 2 }).run();
    if (command === 'formula') editor.chain().focus().insertContent(formulaNode()).run();
    if (command === 'table') editor.chain().focus().insertContent(richTableNode()).run();
    if (command === 'image') {
      if (onRequestImage) onRequestImage();
      else fileInputRef.current?.click();
    }
    setSlashMenuOpen(false);
  };

  return (
    <div className={`pv-tiptap-editor ${compact ? 'pv-tiptap-editor--compact' : ''}`}>
      {showToolbar && <div className="pv-tiptap-toolbar" role="toolbar" aria-label="文本格式">
        <EditorButton label="撤销" disabled={!editor.can().undo()} onClick={() => editor.chain().focus().undo().run()}><Undo2 size={14} /></EditorButton>
        <EditorButton label="重做" disabled={!editor.can().redo()} onClick={() => editor.chain().focus().redo().run()}><Redo2 size={14} /></EditorButton>
        <span className="pv-tiptap-divider" />
        {!compact && <EditorButton label="二级标题" active={editor.isActive('heading', { level: 2 })} onClick={() => editor.chain().focus().toggleHeading({ level: 2 }).run()}><Heading2 size={14} /></EditorButton>}
        <EditorButton label="加粗" active={editor.isActive('bold')} onClick={() => editor.chain().focus().toggleBold().run()}><Bold size={14} /></EditorButton>
        <EditorButton label="斜体" active={editor.isActive('italic')} onClick={() => editor.chain().focus().toggleItalic().run()}><Italic size={14} /></EditorButton>
        {!compact && <EditorButton label="项目符号" active={editor.isActive('bulletList')} onClick={() => editor.chain().focus().toggleBulletList().run()}><List size={14} /></EditorButton>}
        {!compact && <EditorButton label="编号列表" active={editor.isActive('orderedList')} onClick={() => editor.chain().focus().toggleOrderedList().run()}><ListOrdered size={14} /></EditorButton>}
        {!compact && <EditorButton label="引用" active={editor.isActive('blockquote')} onClick={() => editor.chain().focus().toggleBlockquote().run()}><Quote size={14} /></EditorButton>}
        <EditorButton label="插入公式模板" onClick={() => editor.chain().focus().insertContent(formulaNode()).run()}><Sigma size={14} /></EditorButton>
        {!compact && <EditorButton label="插入表格" onClick={() => editor.chain().focus().insertContent(richTableNode()).run()}><Table2 size={14} /></EditorButton>}
        {!compact && <EditorButton label={onRequestImage ? '从图片缓存插入' : '上传图片'} onClick={() => onRequestImage ? onRequestImage() : fileInputRef.current?.click()}><ImagePlus size={14} /></EditorButton>}
        {!compact && figures.map((figure) => (
          <EditorButton key={figure.fig_uuid} label={`插入题图 ${figure.fig_uuid}`} onClick={() => editor.chain().focus().insertContent(figureNode(figure.fig_uuid, imageFileUrl(figure.local_path) || '', Number(figure.display_scale ?? 60), figure.display_align || 'center')).run()}><ImagePlus size={14} /></EditorButton>
        ))}
        <EditorButton label="清除格式" onClick={() => editor.chain().focus().unsetAllMarks().clearNodes().run()}><Eraser size={14} /></EditorButton>
      </div>}
      <input ref={fileInputRef} className="hidden" type="file" tabIndex={-1} aria-hidden="true" accept="image/png,image/jpeg,image/gif,image/webp,image/svg+xml" onChange={(event) => {
        const file = event.target.files?.[0];
        if (file) insertImage(file);
        event.target.value = '';
      }} />
      {slashMenuOpen && (
        <div className="pv-tiptap-slash-menu" role="menu" aria-label="插入内容">
          <button type="button" role="menuitem" onClick={() => runSlashCommand('heading')}><Heading2 size={14} />标题</button>
          <button type="button" role="menuitem" onClick={() => runSlashCommand('formula')}><Sigma size={14} />公式</button>
          <button type="button" role="menuitem" onClick={() => runSlashCommand('table')}><Table2 size={14} />表格</button>
          <button type="button" role="menuitem" onClick={() => runSlashCommand('image')}><ImagePlus size={14} />图片</button>
        </div>
      )}
      <EditorContent editor={editor} style={{ minHeight }} />
      <div className="pv-tiptap-status">{editor.getText().length} 字{compact ? '' : ' · 结构化内容已同步'}</div>
    </div>
  );
}

function EditorButton({ label, active = false, disabled = false, onClick, children }: { label: string; active?: boolean; disabled?: boolean; onClick: () => void; children: ReactNode }) {
  return <button type="button" title={label} aria-label={label} aria-pressed={active} disabled={disabled} onClick={onClick} className={`pv-tiptap-tool ${active ? 'is-active' : ''}`}>{children}</button>;
}
