import type { Figure } from '../../types';
import LatexRenderer from '../render/LatexRenderer';

interface Props {
  title: string;
  figures: Figure[];
  maxImageHeight?: number;
}

/**
 * Render a question stem with ![fig:uuid] placeholders.
 * Each placeholder becomes an image from the import media library.
 */
export default function ImportStemRenderer({ title, figures, maxImageHeight = 180 }: Props) {
  const parts = title.split(/(!\[fig:[^\]]+\])/g);

  return (
    <div>
      {parts.map((part, i) => {
        const match = part.match(/!\[fig:([^\]]+)\]/);
        if (match) {
          const fig = figures.find((item) => item.fig_uuid === match[1]);
          if (!fig) {
            return (
              <span
                key={i}
                className="my-1 inline-flex items-center rounded border border-dashed px-2 py-1 text-xs"
                style={{ borderColor: 'var(--color-red)', color: 'var(--color-red)' }}
              >
                图片缺失 {match[1].slice(0, 12)}
              </span>
            );
          }
          return (
            <span key={i} className="my-1 block">
              <img
                src={`/files/${fig.local_path}`}
                alt={fig.fig_uuid}
                style={{
                  maxWidth: '60%',
                  maxHeight: maxImageHeight,
                  objectFit: 'contain',
                  borderRadius: 6,
                  border: '1px solid var(--color-border)',
                  display: 'block',
                }}
                onError={(event) => {
                  (event.target as HTMLImageElement).style.display = 'none';
                }}
              />
            </span>
          );
        }
        if (!part.trim()) return null;
        return <LatexRenderer key={i} text={part} />;
      })}
    </div>
  );
}
