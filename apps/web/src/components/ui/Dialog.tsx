import type { ReactNode, MouseEvent } from 'react';
import { useEffect, useCallback } from 'react';

interface DialogProps {
  open: boolean;
  onClose: () => void;
  title?: string;
  children: ReactNode;
  size?: 'sm' | 'md' | 'lg';
  className?: string;
}

const sizeStyles = {
  sm: 'max-w-sm',
  md: 'max-w-lg',
  lg: 'max-w-2xl',
};

export function Dialog({ open, onClose, title, children, size = 'md', className = '' }: DialogProps) {
  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    },
    [onClose],
  );

  useEffect(() => {
    if (open) {
      document.addEventListener('keydown', handleKeyDown);
      document.body.style.overflow = 'hidden';
    }
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      document.body.style.overflow = '';
    };
  }, [open, handleKeyDown]);

  if (!open) return null;

  const hasCustomWidth =
    /\bmax-w-/.test(className) ||
    /\bw-\[/.test(className) ||
    /\bw-full\b/.test(className);

  const sizeClass = hasCustomWidth ? '' : sizeStyles[size];

  const handleOverlayClick = (e: MouseEvent) => {
    if (e.target === e.currentTarget) onClose();
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      onClick={handleOverlayClick}
    >
      {/* Overlay */}
      <div className="fixed inset-0 bg-black/40 backdrop-blur-sm animate-in fade-in duration-200" />

      {/* Dialog panel */}
      <div
        className={`
          relative z-10 w-full ${sizeClass} rounded-xl
          border border-[var(--color-border)] bg-[var(--color-bg-card)]
          shadow-[var(--shadow-lg)]
          animate-in zoom-in-95 fade-in duration-200
          ${className}
        `.trim()}
      >
        {title && (
          <div className="flex items-center justify-between border-b border-[var(--color-border)] px-5 py-4">
            <h2 className="text-base font-semibold text-[var(--color-text)]">{title}</h2>
            <button
              onClick={onClose}
              className="inline-flex h-7 w-7 items-center justify-center rounded-md
                text-[var(--color-text-muted)] transition-colors duration-150
                hover:bg-[var(--color-bg-hover)] hover:text-[var(--color-text)]
                cursor-pointer"
            >
              <svg width="15" height="15" viewBox="0 0 15 15" fill="none" stroke="currentColor" strokeWidth="1.5">
                <path d="M3.75 3.75l7.5 7.5M11.25 3.75l-7.5 7.5" strokeLinecap="round" />
              </svg>
            </button>
          </div>
        )}
        <div className="px-5 py-4">{children}</div>
      </div>
    </div>
  );
}

/* ---------- Actions footer ---------- */

interface ActionsProps {
  children: ReactNode;
  className?: string;
}

function Actions({ children, className = '' }: ActionsProps) {
  return (
    <div
      className={`flex items-center justify-end gap-2 border-t border-[var(--color-border)] px-5 py-3 ${className}`}
    >
      {children}
    </div>
  );
}

Dialog.Actions = Actions;
