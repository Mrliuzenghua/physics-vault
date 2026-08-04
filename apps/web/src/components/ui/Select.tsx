import type { SelectHTMLAttributes } from 'react';

interface SelectOption {
  value: string;
  label: string;
}

interface SelectProps extends Omit<SelectHTMLAttributes<HTMLSelectElement>, 'size'> {
  label?: string;
  error?: string;
  options: SelectOption[];
  placeholder?: string;
  size?: 'sm' | 'md';
  wrapperClassName?: string;
}

const sizeStyles = {
  sm: 'h-7 text-xs pl-2.5 pr-7',
  md: 'h-9 text-sm pl-3 pr-8',
};

export function Select({
  label,
  error,
  options,
  placeholder,
  size = 'md',
  className = '',
  wrapperClassName = '',
  id,
  value,
  ...props
}: SelectProps) {
  const selectId = id || label?.replace(/\s+/g, '-').toLowerCase();
  const hasError = Boolean(error);

  return (
    <div className={`flex flex-col gap-1 ${wrapperClassName}`}>
      {label && (
        <label
          htmlFor={selectId}
          className="text-xs font-medium text-[var(--color-text-secondary)] select-none"
        >
          {label}
        </label>
      )}
      <div className="relative">
        <select
          id={selectId}
          value={value}
          className={`
            w-full appearance-none rounded-md border bg-[var(--color-bg-card)]
            text-[var(--color-text)] outline-none transition-colors duration-150 cursor-pointer
            hover:border-[var(--color-border-strong)]
            focus:border-[var(--color-accent)] focus:ring-1 focus:ring-[var(--color-accent)]/20
            ${hasError ? 'border-[var(--color-red)]' : 'border-[var(--color-border)]'}
            ${sizeStyles[size]}
            ${className}
          `.trim()}
          {...props}
        >
          {placeholder && (
            <option value="" disabled>
              {placeholder}
            </option>
          )}
          {options.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
        {/* Custom chevron */}
        <svg
          className={`
            pointer-events-none absolute right-0 top-1/2 -translate-y-1/2 text-[var(--color-text-muted)]
            ${size === 'sm' ? 'w-7 h-3' : 'w-8 h-4'}
          `}
          viewBox="0 0 16 16"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
        >
          <path d="M4 6l4 4 4-4" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </div>
      {error && <p className="text-xs text-[var(--color-red)] leading-tight">{error}</p>}
    </div>
  );
}
