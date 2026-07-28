import type { ReactNode } from 'react';

interface TagProps {
  children: ReactNode;
  removable?: boolean;
  onRemove?: () => void;
  variant?: 'default' | 'accent';
  size?: 'sm' | 'md';
  className?: string;
}

const variantStyles = {
  default: 'bg-[var(--color-bg-code)] text-[var(--color-text-secondary)]',
  accent: 'bg-[var(--color-accent-light)] text-[var(--color-accent-dark)]',
};

const sizeStyles = {
  sm: 'px-1.5 py-0.5 text-[11px]',
  md: 'px-2 py-1 text-xs',
};

export function Tag({
  children,
  removable = false,
  onRemove,
  variant = 'accent',
  size = 'sm',
  className = '',
}: TagProps) {
  return (
    <span
      className={`
        inline-flex items-center gap-1 rounded-md font-medium leading-none
        transition-colors duration-150
        ${variantStyles[variant]}
        ${sizeStyles[size]}
        ${removable ? 'pr-1' : ''}
        ${className}
      `.trim()}
    >
      {children}
      {removable && (
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            onRemove?.();
          }}
          className="inline-flex items-center justify-center rounded-sm p-0.5
            hover:bg-black/10 transition-colors duration-100 cursor-pointer"
          aria-label="移除"
        >
          <svg width="10" height="10" viewBox="0 0 10 10" fill="none" stroke="currentColor" strokeWidth="1.5">
            <path d="M2.5 2.5l5 5M7.5 2.5l-5 5" strokeLinecap="round" />
          </svg>
        </button>
      )}
    </span>
  );
}
