import { useMemo, type CSSProperties } from 'react';
import katex from 'katex';
import { normalizeShortInlineDisplayMath } from '../../utils/mathText';

interface Props {
  text: string;
  className?: string;
  inline?: boolean;
  style?: CSSProperties;
}

/**
 * Render mixed text containing LaTeX math expressions.
 * Inline math uses $...$ and display math uses $$...$$.
 */
export default function LatexRenderer({ text, className, inline, style }: Props) {
  const html = useMemo(() => renderMixed(text), [text]);

  if (inline) {
    return <span className={className} style={style} dangerouslySetInnerHTML={{ __html: html }} />;
  }

  return <div className={className} style={style} dangerouslySetInnerHTML={{ __html: html }} />;
}

interface Segment {
  kind: 'text' | 'math';
  raw: string;
  display?: boolean;
}

function renderMixed(source: string): string {
  return splitTableBlocks(cleanVisibleMathArtifacts(normalizeShortInlineDisplayMath(source)))
    .map((block) => (block.kind === 'table' ? renderMarkdownTable(block.lines) : renderInlineMixed(block.text)))
    .join('');
}

function renderInlineMixed(source: string): string {
  const segments = splitSegments(source);
  return segments
    .map((seg) => {
      if (seg.kind === 'text') return renderPlainText(seg.raw);
      try {
        return katex.renderToString(cleanLatex(seg.raw).trim(), {
          displayMode: seg.display ?? false,
          throwOnError: false,
          strict: false,
        });
      } catch {
        return escapeHtml(seg.raw);
      }
    })
    .join('');
}

interface TextBlock {
  kind: 'text';
  text: string;
}

interface TableBlock {
  kind: 'table';
  lines: string[];
}

function splitTableBlocks(source: string): Array<TextBlock | TableBlock> {
  const lines = source.replace(/\r\n/g, '\n').replace(/\r/g, '\n').split('\n');
  const blocks: Array<TextBlock | TableBlock> = [];
  const textBuffer: string[] = [];

  const flushText = () => {
    if (textBuffer.length === 0) return;
    blocks.push({ kind: 'text', text: textBuffer.join('\n') });
    textBuffer.length = 0;
  };

  let index = 0;
  while (index < lines.length) {
    const line = lines[index];
    const next = lines[index + 1] ?? '';
    if (looksLikeTableRow(line) && looksLikeTableSeparator(next)) {
      flushText();
      const tableLines = [line, next];
      index += 2;
      while (index < lines.length && looksLikeTableRow(lines[index])) {
        tableLines.push(lines[index]);
        index += 1;
      }
      blocks.push({ kind: 'table', lines: tableLines });
      continue;
    }
    if (looksLikeOcrTableBorder(line)) {
      const ocrTable = parseOcrTable(lines, index);
      if (ocrTable) {
        flushText();
        blocks.push({ kind: 'table', lines: ocrTable.tableLines });
        index = ocrTable.nextIndex;
        continue;
      }
    }
    textBuffer.push(line);
    index += 1;
  }
  flushText();
  return blocks;
}

function looksLikeTableRow(line: string): boolean {
  return line.includes('|') && line.split('|').filter((cell) => cell.trim()).length >= 2;
}

function looksLikeTableSeparator(line: string): boolean {
  const cells = trimTableEdges(line).split('|').map((cell) => cell.trim());
  return cells.length >= 2 && cells.every((cell) => /^:?-{3,}:?$/.test(cell));
}

function renderMarkdownTable(lines: string[]): string {
  const rows = lines.map(parseTableRow);
  const header = rows[0] ?? [];
  const body = rows.slice(2);
  const headHtml = header.map((cell) => `<th>${renderInlineMixed(cell)}</th>`).join('');
  const bodyHtml = body
    .map((row) => `<tr>${row.map((cell) => `<td>${renderInlineMixed(cell)}</td>`).join('')}</tr>`)
    .join('');
  return `<div class="markdown-table-wrap"><table><thead><tr>${headHtml}</tr></thead><tbody>${bodyHtml}</tbody></table></div>`;
}

function parseTableRow(line: string): string[] {
  return trimTableEdges(line).split('|').map((cell) => cell.trim());
}

function trimTableEdges(line: string): string {
  return line.trim().replace(/^\|/, '').replace(/\|$/, '');
}

function looksLikeOcrTableBorder(line: string): boolean {
  return /^\s*-{3,}(?:\s+-{3,})+\s*$/.test(line);
}

function parseOcrTable(lines: string[], startIndex: number): { tableLines: string[]; nextIndex: number } | null {
  const headerBorder = lines[startIndex] ?? '';
  const columnCount = (headerBorder.match(/-{3,}/g) ?? []).length;
  if (columnCount < 2) return null;

  let endIndex = startIndex + 1;
  while (endIndex < lines.length && !looksLikeOcrTableBorder(lines[endIndex])) {
    endIndex += 1;
  }
  if (endIndex >= lines.length) return null;

  const bodyLines = lines
    .slice(startIndex + 1, endIndex)
    .map((line) => line.trim())
    .filter(Boolean);
  if (bodyLines.length < 2) return null;

  const rows = bodyLines.map((line) => splitOcrTableRow(line, columnCount));
  if (rows.some((row) => row === null)) return null;

  const tableLines = [
    markdownTableRow(rows[0] ?? []),
    markdownTableRow(Array.from({ length: columnCount }, () => '---')),
    ...rows.slice(1).map((row) => markdownTableRow(row ?? [])),
  ];
  return { tableLines, nextIndex: endIndex + 1 };
}

function splitOcrTableRow(line: string, columnCount: number): string[] | null {
  const mathCells = line.match(/\$[^$]+\$/g) ?? [];
  if (mathCells.length === columnCount) {
    const leftover = mathCells.reduce((rest, cell) => rest.replace(cell, ' '), line).trim();
    if (!leftover) return mathCells.map((cell) => cell.trim());
  }

  const wideSpaceCells = line.trim().split(/\t+|\s{2,}/).filter(Boolean);
  if (wideSpaceCells.length === columnCount) return wideSpaceCells;

  if (columnCount === 2) {
    const compactCells = line.trim().split(/\s+/).filter(Boolean);
    if (compactCells.length === 2) return compactCells;
  }

  return null;
}

function markdownTableRow(cells: string[]): string {
  return `| ${cells.map((cell) => cell.replace(/\|/g, '\\|')).join(' | ')} |`;
}

function splitSegments(source: string): Segment[] {
  if (!source) return [{ kind: 'text', raw: '' }];
  const segments: Segment[] = [];
  const re = /\$\$([\s\S]+?)\$\$|\\\[([\s\S]+?)\\\]|\\\(([\s\S]+?)\\\)|\$([\s\S]+?)\$/g;
  let cursor = 0;
  let match: RegExpExecArray | null;

  while ((match = re.exec(source)) !== null) {
    if (match.index > cursor) {
      segments.push({ kind: 'text', raw: source.slice(cursor, match.index) });
    }
    const displayMath = match[1] ?? match[2];
    const inlineMath = match[3] ?? match[4];
    segments.push({
      kind: 'math',
      raw: displayMath ?? inlineMath ?? '',
      display: displayMath !== undefined,
    });
    cursor = match.index + match[0].length;
  }

  if (cursor < source.length) {
    segments.push({ kind: 'text', raw: source.slice(cursor) });
  }

  return segments;
}

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function renderPlainText(s: string): string {
  return renderBasicMarkdownText(escapeHtml(cleanVisibleTextArtifacts(s)))
    .replace(/!\[([^\]]*)\]\((data:image\/(?:png|jpeg|jpg|gif|webp|svg\+xml);base64,[A-Za-z0-9+/=]+|\/files\/[^)\s]+)\)/g, '<img class="rich-inline-image" src="$2" alt="$1" />')
    .replace(/\r\n/g, '\n')
    .replace(/\r/g, '\n')
    .replace(/\n/g, '<br />');
}

function renderBasicMarkdownText(s: string): string {
  return s
    .replace(/^#{1,3}\s+(.+)$/gm, '<strong>$1</strong>')
    .replace(/^\s*[-•]\s+/gm, '• ')
    .replace(/^>\s?/gm, '│ ')
    .replace(/\*\*([^*\n]+?)\*\*/g, '<strong>$1</strong>')
    .replace(/~~([^~\n]+?)~~/g, '<s>$1</s>')
    .replace(/(^|[^*])\*([^*\n]+?)\*(?!\*)/g, '$1<em>$2</em>')
    .replace(/`([^`\n]+?)`/g, '<code>$1</code>');
}

function cleanLatex(value: string): string {
  return value
    .replace(/\\?mspace\s*\{?\s*-?\d+(?:\.\d+)?\s*(?:mu|em|pt)\s*\}?/gi, '\\,')
    .replace(/\\?mspace\s*-?\d+(?:\.\d+)?\s*(?:mu|em|pt)/gi, '\\,');
}

function cleanVisibleMathArtifacts(value: string): string {
  return value
    .replace(/\\?mspace\s*\{?\s*-?\d+(?:\.\d+)?\s*(?:mu|em|pt)\s*\}?/gi, ' ')
    .replace(/\\?mspace\s*-?\d+(?:\.\d+)?\s*(?:mu|em|pt)/gi, ' ');
}

function cleanVisibleTextArtifacts(value: string): string {
  return cleanVisibleMathArtifacts(value)
    .replace(/(?:\\_){2,}/g, (match) => '_'.repeat(match.length / 2));
}
