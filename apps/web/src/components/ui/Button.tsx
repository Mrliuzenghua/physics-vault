import type { ButtonHTMLAttributes, ReactNode } from 'react';
import { Spinner } from './Spinner';

type ButtonVariant = 'primary' | 'secondary' | 'outline' | 'ghost' | 'danger';
type ButtonSize = 'sm' | 'md' | 'lg';

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
  icon?: ReactNode;
  children: ReactNode;
}

const variantStyles: Record<ButtonVariant, string> = {
  primary:
    'bg-[var(--color-accent)] text-white shadow-[0_1px_2px_rgba(20,50,110,0.22),inset_0_1px_0_rgba(255,255,255,0.12)] hover:bg-[var(--color-accent-dark)] active:scale-[0.98] focus-visible:ring-[var(--color-accent)]/40',
  secondary:
    'bg-[var(--color-bg-hover)] text-[var(--color-text)] hover:bg-[var(--color-border)] active:scale-[0.98] focus-visible:ring-[var(--color-border)]',
  outline:
    'border border-[var(--color-border)] bg-transparent text-[var(--color-text)] hover:bg-[var(--color-bg-hover)] hover:border-[var(--color-border-strong)] active:scale-[0.98] focus-visible:ring-[var(--color-border)]',
  ghost:
    'bg-transparent text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-hover)] hover:text-[var(--color-text)] focus-visible:ring-[var(--color-border)]',
  danger:
    'bg-[var(--color-red)] text-white shadow-[0_1px_2px_rgba(120,20,20,0.22),inset_0_1px_0_rgba(255,255,255,0.12)] hover:bg-[#c53030] active:scale-[0.98] focus-visible:ring-[var(--color-red)]/40',
};

const sizeStyles: Record<ButtonSize, string> = {
  sm: 'h-7 px-2.5 text-xs gap-1 rounded-md',
  md: 'h-8 px-3.5 text-sm gap-1.5 rounded-lg',
  lg: 'h-10 px-5 text-sm gap-2 rounded-lg',
};

export function Button({
  variant = 'primary',
  size = 'md',
  loading = false,
  icon,
  children,
  disabled,
  className = '',
  ...props
}: ButtonProps) {
  const isDisabled = disabled || loading;

  return (
    <button
      className={`
        inline-flex items-center justify-center font-medium
        transition-all duration-200 ease-out
        focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-1 focus-visible:ring-offset-[var(--color-bg)]
        disabled:cursor-not-allowed disabled:opacity-50
        cursor-pointer select-none
        ${variantStyles[variant]}
        ${sizeStyles[size]}
        ${className}
      `.trim()}
      disabled={isDisabled}
      {...props}
    >
      {loading ? (
        <Spinner size={size === 'sm' ? 14 : 16} />
      ) : icon ? (
        <span className="shrink-0 inline-flex items-center">{icon}</span>
      ) : null}
      {children}
    </button>
  );
}
