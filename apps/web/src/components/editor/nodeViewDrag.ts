import type { Editor } from '@tiptap/core';
import type { Node as ProseMirrorNode } from '@tiptap/pm/model';
import { NodeSelection } from '@tiptap/pm/state';

/** Move an atom node to the document position under the pointer. */
export function moveNodeToPointer(
  editor: Editor,
  getPos: () => number | undefined,
  node: ProseMirrorNode,
  clientX: number,
  clientY: number,
): boolean {
  const from = getPos();
  if (from === undefined) return false;
  const point = editor.view.posAtCoords({ left: clientX, top: clientY });
  if (!point) return false;

  const target = point.pos;
  if (target >= from && target <= from + node.nodeSize) return false;

  const insertionPos = target > from ? target - node.nodeSize : target;
  const transaction = editor.state.tr
    .delete(from, from + node.nodeSize)
    .insert(insertionPos, node);
  transaction.setSelection(NodeSelection.create(transaction.doc, insertionPos));
  editor.view.dispatch(transaction);
  editor.view.focus();
  return true;
}
