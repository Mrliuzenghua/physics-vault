import { NodeViewWrapper, type NodeViewProps } from '@tiptap/react';
import type { ChangeEvent } from 'react';
import { decodeMathHtmlEntities } from '../../utils/mathText';

/** Formula source stays directly editable in the editor. */
export default function QuestionFormulaView({ node, selected, updateAttributes }: NodeViewProps) {
  const value = decodeMathHtmlEntities(String(node.attrs.latex || ''));

  return (
    <NodeViewWrapper
      as="span"
      className={`pv-tiptap-formula-node ${selected ? 'is-selected' : ''}`}
      contentEditable={false}
    >
      <span className="pv-tiptap-formula-prefix">$</span>
      <input
        value={value}
        aria-label="编辑 LaTeX 公式"
        onChange={(event: ChangeEvent<HTMLInputElement>) => updateAttributes({ latex: event.target.value })}
      />
      <span className="pv-tiptap-formula-prefix">$</span>
    </NodeViewWrapper>
  );
}
