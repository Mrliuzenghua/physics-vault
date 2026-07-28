import { useState } from 'react';

interface Props {
  value: number;        // 0-5
  onChange?: (stars: number) => void;
  readonly?: boolean;
  size?: number;
}

export default function StarRating({ value, onChange, readonly, size = 14 }: Props) {
  const [hover, setHover] = useState(0);

  return (
    <span style={{ display: 'inline-flex', gap: 1, alignItems: 'center' }}>
      {[1, 2, 3, 4, 5].map((star) => {
        const filled = star <= (hover || value);
        return (
          <button
            key={star}
            type="button"
            disabled={readonly}
            onClick={() => onChange?.(star === value ? 0 : star)}
            onMouseEnter={() => !readonly && setHover(star)}
            onMouseLeave={() => !readonly && setHover(0)}
            style={{
              cursor: readonly ? 'default' : 'pointer',
              background: 'none',
              border: 'none',
              padding: 0,
              fontSize: size,
              lineHeight: 1,
              color: filled ? '#f5a623' : 'var(--color-border)',
              transition: 'color 0.15s',
            }}
            title={`${star} 星`}
          >
            ★
          </button>
        );
      })}
    </span>
  );
}
