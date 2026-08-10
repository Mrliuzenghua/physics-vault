import { NodeViewWrapper, type NodeViewProps } from '@tiptap/react';
import { AlignCenter, AlignLeft, AlignRight, GripVertical, Minus, Plus, Trash2 } from 'lucide-react';
import { useEffect, useRef, useState, type PointerEvent as ReactPointerEvent } from 'react';
import { moveNodeToPointer } from './nodeViewDrag';

const MIN_SCALE = 25;
const MAX_SCALE = 100;

function clampScale(value: number): number {
  return Math.min(MAX_SCALE, Math.max(MIN_SCALE, Math.round(value)));
}

/**
 * A real, selectable image node for question figures. The drag handle changes
 * the persisted displayScale attribute, rather than applying a temporary CSS
 * transform, so the live preview and exports receive the same size.
 */
export default function QuestionFigureView({ node, selected, updateAttributes, deleteNode, editor, getPos }: NodeViewProps) {
  const wrapperRef = useRef<HTMLSpanElement | null>(null);
  const cleanupDragRef = useRef<(() => void) | null>(null);
  const cleanupMoveRef = useRef<((event?: PointerEvent) => void) | null>(null);
  const [hovered, setHovered] = useState(false);
  const [dragging, setDragging] = useState(false);
  const scale = clampScale(Number(node.attrs.displayScale ?? 60));
  const align = (['left', 'center', 'right'].includes(String(node.attrs.displayAlign)) ? node.attrs.displayAlign : 'center') as 'left' | 'center' | 'right';
  const src = String(node.attrs.src || '');
  const figureId = String(node.attrs.figureId || '');

  useEffect(() => () => {
    cleanupDragRef.current?.();
    cleanupMoveRef.current?.();
  }, []);

  const beginMove = (event: ReactPointerEvent<HTMLButtonElement>) => {
    event.preventDefault();
    event.stopPropagation();
    cleanupDragRef.current?.();
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
    setDragging(false);
  };

  const beginResize = (event: ReactPointerEvent<HTMLButtonElement>) => {
    event.preventDefault();
    event.stopPropagation();
    cleanupDragRef.current?.();
    const startX = event.clientX;
    const startScale = scale;
    const containerWidth = Math.max(180, wrapperRef.current?.parentElement?.getBoundingClientRect().width || 1);
    const onMove = (moveEvent: PointerEvent) => {
      const next = clampScale(startScale + ((moveEvent.clientX - startX) / containerWidth) * 100);
      updateAttributes({ displayScale: next });
    };
    const onUp = () => {
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
      cleanupDragRef.current = null;
      setDragging(false);
    };
    cleanupDragRef.current = onUp;
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp, { once: true });
    setDragging(true);
  };

  if (!src) {
    return <NodeViewWrapper as="span" className="pv-tiptap-figure-node">图 {figureId}</NodeViewWrapper>;
  }

  return (
    <NodeViewWrapper
      as="span"
      ref={wrapperRef}
      className={`pv-tiptap-image-node ${selected ? 'is-selected' : ''} ${dragging ? 'is-dragging' : ''}`}
      style={{
        width: `${scale}%`,
        marginLeft: align === 'left' ? 0 : 'auto',
        marginRight: align === 'right' ? 0 : 'auto',
      }}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => !dragging && setHovered(false)}
      data-figure-id={figureId}
    >
      <img src={src} alt={`题图 ${figureId}`} draggable={false} />
      {(selected || hovered || dragging) && (
        <>
          <span className="pv-tiptap-image-actions" contentEditable={false}>
            <button type="button" aria-label="拖动图片位置" title="按住拖动图片位置" data-drag-handle onPointerDown={beginMove}><GripVertical size={13} /></button>
            <span className="pv-tiptap-image-actions__divider" />
            <button type="button" className={align === 'left' ? 'is-active' : ''} aria-label="图片左对齐" title="左对齐" onClick={() => updateAttributes({ displayAlign: 'left' })}><AlignLeft size={13} /></button>
            <button type="button" className={align === 'center' ? 'is-active' : ''} aria-label="图片居中" title="居中" onClick={() => updateAttributes({ displayAlign: 'center' })}><AlignCenter size={13} /></button>
            <button type="button" className={align === 'right' ? 'is-active' : ''} aria-label="图片右对齐" title="右对齐" onClick={() => updateAttributes({ displayAlign: 'right' })}><AlignRight size={13} /></button>
            <span className="pv-tiptap-image-actions__divider" />
            <button type="button" aria-label="缩小图片" title="缩小 10%" onClick={() => updateAttributes({ displayScale: clampScale(scale - 10) })}><Minus size={13} /></button>
            <button type="button" aria-label="放大图片" title="放大 10%" onClick={() => updateAttributes({ displayScale: clampScale(scale + 10) })}><Plus size={13} /></button>
            <button type="button" className="is-danger" aria-label="删除图片" title="删除图片" onClick={deleteNode}><Trash2 size={13} /></button>
          </span>
          <span className="pv-tiptap-image-size">{scale}%</span>
          <button
            type="button"
            className="pv-tiptap-image-resize-handle"
            aria-label="拖拽调整图片大小"
            title="拖拽调整图片大小"
            contentEditable={false}
            onPointerDown={beginResize}
          />
        </>
      )}
    </NodeViewWrapper>
  );
}
