import type { ReactNode } from 'react';

type BadgeVariant = 'default' | 'success' | 'warning' | 'danger' | 'info' | 'purple' | 'teal' | 'accent';
type BadgeSize = 'sm' | 'md';

interface BadgeProps {
  children: ReactNode;
  variant?: BadgeVariant;
  size?: BadgeSize;
  dot?: boolean;
  className?: string;
}

const variantStyles: Record<BadgeVariant, string> = {
  default: 'bg-[var(--color-bg-code)] text-[var(--color-text-secondary)]',
  success: 'bg-[var(--color-green-light)] text-[var(--color-green)]',
  warning: 'bg-[var(--color-orange-light)] text-[var(--color-orange)]',
  danger: 'bg-[var(--color-red-light)] text-[var(--color-red)]',
  info: 'bg-[var(--color-accent-light)] text-[var(--color-accent)]',
  purple: 'bg-[var(--color-purple-light)] text-[var(--color-purple)]',
  teal: 'bg-[var(--color-teal-light)] text-[var(--color-teal)]',
  accent: 'bg-[var(--color-accent-light)] text-[var(--color-accent-dark)]',
};

const dotColors: Record<BadgeVariant, string> = {
  default: 'var(--color-text-muted)',
  success: 'var(--color-green)',
  warning: 'var(--color-orange)',
  danger: 'var(--color-red)',
  info: 'var(--color-accent)',
  purple: 'var(--color-purple)',
  teal: 'var(--color-teal)',
  accent: 'var(--color-accent)',
};

const sizeStyles: Record<BadgeSize, string> = {
  sm: 'px-1.5 py-0.5 text-[11px]',
  md: 'px-2 py-0.5 text-xs',
};

export function Badge({ children, variant = 'default', size = 'md', dot = false, className = '' }: BadgeProps) {
  return (
    <span
      className={`
        inline-flex items-center gap-1 rounded-full font-semibold leading-none
        transition-colors duration-150
        ${variantStyles[variant]}
        ${sizeStyles[size]}
        ${className}
      `.trim()}
    >
      {dot && (
        <span
          className="inline-block h-1.5 w-1.5 rounded-full shrink-0"
          style={{ backgroundColor: dotColors[variant] }}
        />
      )}
      {children}
    </span>
  );
}
