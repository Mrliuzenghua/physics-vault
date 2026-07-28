import type { InputHTMLAttributes, ReactNode } from 'react';

interface InputProps extends Omit<InputHTMLAttributes<HTMLInputElement>, 'size'> {
  label?: string;
  error?: string;
  helperText?: string;
  leftIcon?: ReactNode;
  rightIcon?: ReactNode;
  size?: 'sm' | 'md';
  wrapperClassName?: string;
}

const sizeStyles = {
  sm: 'h-7 text-xs px-2.5',
  md: 'h-9 text-sm px-3',
};

const iconSizeStyles = {
  sm: 'pl-7',
  md: 'pl-9',
};

const rightIconSizeStyles = {
  sm: 'pr-7',
  md: 'pr-9',
};

export function Input({
  label,
  error,
  helperText,
  leftIcon,
  rightIcon,
  size = 'md',
  className = '',
  wrapperClassName = '',
  id,
  ...props
}: InputProps) {
  const inputId = id || label?.replace(/\s+/g, '-').toLowerCase();
  const hasError = Boolean(error);

  return (
    <div className={`flex flex-col gap-1 ${wrapperClassName}`}>
      {label && (
        <label
          htmlFor={inputId}
          className="text-xs font-medium text-[var(--color-text-secondary)] select-none"
        >
          {label}
        </label>
      )}
      <div className="relative">
        {leftIcon && (
          <span
            className={`
              absolute left-0 top-1/2 -translate-y-1/2 flex items-center justify-center
              text-[var(--color-text-muted)]
              ${size === 'sm' ? 'w-7' : 'w-9'}
            `}
          >
            {leftIcon}
          </span>
        )}
        <input
          id={inputId}
          className={`
            w-full rounded-lg border bg-[var(--color-bg-card)] text-[var(--color-text)]
            placeholder:text-[var(--color-text-muted)]
            outline-none transition-all duration-200
            hover:border-[var(--color-border-strong)]
            focus:border-[var(--color-accent)] focus:ring-2 focus:ring-[var(--color-accent)]/15
            ${hasError ? 'border-[var(--color-red)] focus:border-[var(--color-red)] focus:ring-[var(--color-red)]/15' : 'border-[var(--color-border)]'}
            ${sizeStyles[size]}
            ${leftIcon ? iconSizeStyles[size] : ''}
            ${rightIcon ? rightIconSizeStyles[size] : ''}
            ${className}
          `.trim()}
          {...props}
        />
        {rightIcon && (
          <span
            className={`
              absolute right-0 top-1/2 -translate-y-1/2 flex items-center justify-center
              text-[var(--color-text-muted)]
              ${size === 'sm' ? 'w-7' : 'w-9'}
            `}
          >
            {rightIcon}
          </span>
        )}
      </div>
      {error && <p className="text-xs text-[var(--color-red)] leading-tight">{error}</p>}
      {!error && helperText && (
        <p className="text-xs text-[var(--color-text-muted)] leading-tight">{helperText}</p>
      )}
    </div>
  );
}
