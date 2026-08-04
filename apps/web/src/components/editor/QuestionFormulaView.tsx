import { NodeViewWrapper, type NodeViewProps } from '@tiptap/react';
import { useEffect, useRef, useState, type ChangeEvent, type MouseEvent as ReactMouseEvent } from 'react';
import LatexRenderer from '../render/LatexRenderer';
import { decodeMathHtmlEntities } from '../../utils/mathText';

/** A compact, double-click-to-edit inline LaTeX node. */
export default function QuestionFormulaView({ node, selected, updateAttributes }: NodeViewProps) {
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(() => decodeMathHtmlEntities(String(node.attrs.latex || '')));
  const inputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    if (editing) inputRef.current?.focus();
  }, [editing]);

  useEffect(() => {
    if (!editing) setValue(decodeMathHtmlEntities(String(node.attrs.latex || '')));
  }, [editing, node.attrs.latex]);

  const commit = () => {
    const next = decodeMathHtmlEntities(value.trim()) || '...';
    updateAttributes({ latex: next });
    setValue(next);
    setEditing(false);
  };

  if (editing) {
    return (
      <NodeViewWrapper as="span" className="pv-tiptap-formula-editor" contentEditable={false}>
        <span className="pv-tiptap-formula-prefix">$</span>
        <input
          ref={inputRef}
          value={value}
          aria-label="编辑 LaTeX 公式"
          onChange={(event: ChangeEvent<HTMLInputElement>) => setValue(event.target.value)}
          onBlur={commit}
          onKeyDown={(event) => {
            if (event.key === 'Enter') {
              event.preventDefault();
              commit();
            }
            if (event.key === 'Escape') {
              event.preventDefault();
              setValue(decodeMathHtmlEntities(String(node.attrs.latex || '')));
              setEditing(false);
            }
          }}
        />
        <span className="pv-tiptap-formula-prefix">$</span>
        <span className="pv-tiptap-formula-live"><LatexRenderer text={`$${value || '...'}$`} /></span>
      </NodeViewWrapper>
    );
  }

  return (
    <NodeViewWrapper
      as="span"
      className={`pv-tiptap-formula-node ${selected ? 'is-selected' : ''}`}
      contentEditable={false}
      title="双击编辑 LaTeX 公式"
      onDoubleClick={(event: ReactMouseEvent<HTMLSpanElement>) => {
        event.preventDefault();
        setValue(decodeMathHtmlEntities(String(node.attrs.latex || '')));
        setEditing(true);
      }}
    >
      <LatexRenderer text={`$${decodeMathHtmlEntities(String(node.attrs.latex || '...'))}$`} />
    </NodeViewWrapper>
  );
}
