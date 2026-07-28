import { useMemo } from 'react';
import katex from 'katex';

interface Props {
  text: string;
  className?: string;
  inline?: boolean;
}

/**
 * Render mixed text containing LaTeX math expressions.
 * Inline math uses $...$ and display math uses $$...$$.
 */
export default function LatexRenderer({ text, className, inline }: Props) {
  const html = useMemo(() => renderMixed(text), [text]);

  if (inline) {
    return <span className={className} dangerouslySetInnerHTML={{ __html: html }} />;
  }

  return <div className={className} dangerouslySetInnerHTML={{ __html: html }} />;
}

interface Segment {
  kind: 'text' | 'math';
  raw: string;
  display?: boolean;
}

function renderMixed(source: string): string {
  const segments = splitSegments(source);
  return segments
    .map((seg) => {
      if (seg.kind === 'text') return renderText(seg.raw);
      try {
        return katex.renderToString(seg.raw.trim(), {
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

function splitSegments(source: string): Segment[] {
  if (!source) return [{ kind: 'text', raw: '' }];
  const segments: Segment[] = [];
  const re = /\$\$([\s\S]+?)\$\$|\$([\s\S]+?)\$/g;
  let cursor = 0;
  let match: RegExpExecArray | null;

  while ((match = re.exec(source)) !== null) {
    if (match.index > cursor) {
      segments.push({ kind: 'text', raw: source.slice(cursor, match.index) });
    }
    if (match[1] !== undefined) {
      segments.push({ kind: 'math', raw: match[1], display: true });
    } else {
      segments.push({ kind: 'math', raw: match[2], display: false });
    }
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

function renderText(s: string): string {
  return escapeHtml(s)
    .replace(/\r\n/g, '\n')
    .replace(/\r/g, '\n')
    .replace(/\n/g, '<br />');
}
