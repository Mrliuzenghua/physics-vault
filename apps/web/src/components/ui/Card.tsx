import type { ReactNode } from 'react';

interface CardProps {
  children: ReactNode;
  hoverable?: boolean;
  padding?: 'none' | 'sm' | 'md' | 'lg';
  className?: string;
  onClick?: () => void;
}

const paddingStyles = {
  none: '',
  sm: 'p-3',
  md: 'p-4',
  lg: 'p-6',
};

export function Card({ children, hoverable = false, padding = 'md', className = '', onClick }: CardProps) {
  return (
    <div
      className={`
        rounded-[var(--radius-card)] border border-[var(--color-border)]
        bg-[var(--color-bg-card)] shadow-[var(--shadow-card)]
        transition-all duration-150 ease-out
        ${hoverable ? 'hover:-translate-y-0.5 hover:shadow-[var(--shadow-lg)] cursor-pointer' : ''}
        ${paddingStyles[padding]}
        ${className}
      `.trim()}
      onClick={onClick}
    >
      {children}
    </div>
  );
}

/* ---------- compound sub-components ---------- */

interface SectionProps {
  children: ReactNode;
  className?: string;
}

function Header({ children, className = '' }: SectionProps) {
  return (
    <div
      className={`flex items-center justify-between border-b border-[var(--color-border)] pb-3 mb-3 ${className}`}
    >
      {children}
    </div>
  );
}

function Body({ children, className = '' }: SectionProps) {
  return <div className={className}>{children}</div>;
}

function Footer({ children, className = '' }: SectionProps) {
  return (
    <div className={`flex items-center justify-end gap-2 border-t border-[var(--color-border)] pt-3 mt-3 ${className}`}>
      {children}
    </div>
  );
}

Card.Header = Header;
Card.Body = Body;
Card.Footer = Footer;
