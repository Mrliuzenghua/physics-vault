import { Node } from '@tiptap/core';
import { NodeViewWrapper, ReactNodeViewRenderer, type NodeViewProps } from '@tiptap/react';
import { GripVertical, ImagePlus, Minus, Plus } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { moveNodeToPointer } from './nodeViewDrag';

type TableCells = string[][];

function normalizeCells(value: unknown): TableCells {
  if (!Array.isArray(value)) return [['项目', '内容'], ['示例', '']];
  const rows = value.map((row) => Array.isArray(row) ? row.map((cell) => String(cell ?? '')) : []);
  return rows.length >= 2 && rows.every((row) => row.length >= 2) ? rows : [['项目', '内容'], ['示例', '']];
}

function RichImageView({ node, selected, updateAttributes, editor, getPos }: NodeViewProps) {
  const wrapperRef = useRef<HTMLDivElement | null>(null);
  const cleanupMoveRef = useRef<((event?: PointerEvent) => void) | null>(null);
  const [hovered, setHovered] = useState(false);
  const [dragging, setDragging] = useState(false);
  const width = Math.min(100, Math.max(20, Number(node.attrs.width ?? 100)));

  const beginMove = (event: React.PointerEvent<HTMLButtonElement>) => {
    event.preventDefault();
    event.stopPropagation();
    cleanupMoveRef.current?.();
    const startX = event.clientX;
    const startY = event.clientY;
    let moved = false;

    const onMove = (moveEvent: PointerEvent) => {
      if (!moved && Math.hypot(moveEvent.clientX - startX, moveEvent.clientY - startY) < 4) return;
      moved = true;
      setDragging(true);
    };
    const onUp = (upEvent?: PointerEvent) => {
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
      cleanupMoveRef.current = null;
      setDragging(false);
      if (moved && upEvent) moveNodeToPointer(editor, getPos, node, upEvent.clientX, upEvent.clientY);
    };

    cleanupMoveRef.current = onUp;
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp, { once: true });
  };

  const resize = (event: React.PointerEvent<HTMLButtonElement>) => {
    event.preventDefault();
    event.stopPropagation();
    const startX = event.clientX;
    const startWidth = width;
    const parentWidth = Math.max(200, wrapperRef.current?.parentElement?.getBoundingClientRect().width || 1);
    const onMove = (moveEvent: PointerEvent) => {
      updateAttributes({ width: Math.min(100, Math.max(20, Math.round(startWidth + ((moveEvent.clientX - startX) / parentWidth) * 100))) });
    };
    const onUp = () => {
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
      setDragging(false);
    };
    setDragging(true);
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp, { once: true });
  };

  useEffect(() => () => cleanupMoveRef.current?.(), []);

  return (
    <NodeViewWrapper
      as="div"
      ref={wrapperRef}
      className={`pv-rich-image-node ${selected ? 'is-selected' : ''} ${dragging ? 'is-dragging' : ''}`}
      style={{ width: `${width}%` }}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => !dragging && setHovered(false)}
    >
      <img src={String(node.attrs.src || '')} alt={String(node.attrs.alt || '知识点图片')} draggable={false} />
      {(selected || hovered || dragging) && <>
        <button type="button" className="pv-tiptap-image-drag-handle" aria-label="拖动图片位置" title="拖动图片位置" contentEditable={false} data-drag-handle onPointerDown={beginMove}><GripVertical size={12} /></button>
        <span className="pv-rich-image-size">{width}%</span>
        <button type="button" className="pv-rich-image-resize" aria-label="调整图片大小" contentEditable={false} onPointerDown={resize} />
      </>}
    </NodeViewWrapper>
  );
}

function RichTableView({ node, updateAttributes }: NodeViewProps) {
  const cells = normalizeCells(node.attrs.cells);
  const updateCell = (rowIndex: number, cellIndex: number, value: string) => {
    const next = cells.map((row) => [...row]);
    next[rowIndex][cellIndex] = value;
    updateAttributes({ cells: next });
  };
  const addRow = () => updateAttributes({ cells: [...cells, Array.from({ length: cells[0].length }, () => '')] });
  const removeRow = () => cells.length > 2 && updateAttributes({ cells: cells.slice(0, -1) });
  const addColumn = () => updateAttributes({ cells: cells.map((row) => [...row, '']) });
  const removeColumn = () => cells[0].length > 2 && updateAttributes({ cells: cells.map((row) => row.slice(0, -1)) });

  return (
    <NodeViewWrapper as="div" className="pv-rich-table-node" contentEditable={false}>
      <div className="pv-rich-table-toolbar">
        <span>表格</span>
        <div className="pv-rich-table-actions">
          <button type="button" title="添加行" onClick={addRow}><Plus size={12} /> 行</button>
          <button type="button" title="删除行" disabled={cells.length <= 2} onClick={removeRow}><Minus size={12} /> 行</button>
          <button type="button" title="添加列" onClick={addColumn}><Plus size={12} /> 列</button>
          <button type="button" title="删除列" disabled={cells[0].length <= 2} onClick={removeColumn}><Minus size={12} /> 列</button>
        </div>
      </div>
      <div className="pv-rich-table-scroll">
        <table>
          <tbody>
            {cells.map((row, rowIndex) => <tr key={rowIndex}>
              {row.map((cell, cellIndex) => <td key={cellIndex}>
                <input value={cell} onChange={(event) => updateCell(rowIndex, cellIndex, event.target.value)} aria-label={`第 ${rowIndex + 1} 行第 ${cellIndex + 1} 列`} />
              </td>)}
            </tr>)}
          </tbody>
        </table>
      </div>
    </NodeViewWrapper>
  );
}

export const RichImageNode = Node.create({
  name: 'richImage',
  group: 'block',
  atom: true,
  draggable: true,
  addAttributes() {
    return {
      src: { default: '', parseHTML: (element) => element.getAttribute('src') || '', renderHTML: (attrs) => ({ src: attrs.src }) },
      alt: { default: '', parseHTML: (element) => element.getAttribute('alt') || '', renderHTML: (attrs) => ({ alt: attrs.alt }) },
      width: { default: 100, parseHTML: (element) => Number(element.getAttribute('data-rich-image-width') || 100), renderHTML: (attrs) => ({ 'data-rich-image-width': attrs.width }) },
    };
  },
  parseHTML() { return [{ tag: 'img[data-rich-image]' }]; },
  renderHTML({ HTMLAttributes }) { return ['img', { ...HTMLAttributes, 'data-rich-image': 'true' }]; },
  addNodeView() { return ReactNodeViewRenderer(RichImageView); },
});

export const RichTableNode = Node.create({
  name: 'richTable',
  group: 'block',
  atom: true,
  addAttributes() {
    return {
      cells: {
        default: [['项目', '内容'], ['示例', '']],
        parseHTML: (element) => {
          try { return JSON.parse(decodeURIComponent(element.getAttribute('data-rich-table') || '')); } catch { return [['项目', '内容'], ['示例', '']]; }
        },
        renderHTML: (attrs) => ({ 'data-rich-table': encodeURIComponent(JSON.stringify(normalizeCells(attrs.cells))) }),
      },
    };
  },
  parseHTML() { return [{ tag: 'div[data-rich-table]' }]; },
  renderHTML({ HTMLAttributes }) { return ['div', { ...HTMLAttributes }]; },
  addNodeView() { return ReactNodeViewRenderer(RichTableView); },
});

export const RICH_CONTENT_NODES = [RichImageNode, RichTableNode];

export function richImageNode(src: string, alt = '知识点图片') {
  return { type: 'richImage', attrs: { src, alt, width: 100 } };
}

export function richTableNode() {
  return { type: 'richTable', attrs: { cells: [['项目', '内容'], ['示例', '']] } };
}

export { ImagePlus };
