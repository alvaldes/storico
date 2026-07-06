import { forwardRef, type ButtonHTMLAttributes } from 'react';
import { cn } from '@/lib/utils';

type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'outline';
type ButtonSize = 'sm' | 'md' | 'lg';

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
}

const variantStyles: Record<ButtonVariant, string> = {
  primary:
    'bg-(--color-primary-500) text-white hover:bg-(--color-primary-600) focus-visible:ring-(--color-primary-500)',
  secondary:
    'bg-(--color-surface-secondary) text-(--color-text) hover:bg-(--color-border) focus-visible:ring-(--color-primary-500)',
  ghost:
    'bg-transparent text-(--color-text-secondary) hover:bg-(--color-surface-secondary) focus-visible:ring-(--color-primary-500)',
  outline:
    'border border-(--color-border) bg-transparent text-(--color-text) hover:bg-(--color-surface-secondary) focus-visible:ring-(--color-primary-500)',
};

const sizeStyles: Record<ButtonSize, string> = {
  sm: 'px-3 py-1.5 text-sm',
  md: 'px-4 py-2 text-sm',
  lg: 'px-6 py-3 text-base',
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = 'primary', size = 'md', ...props }, ref) => {
    return (
      <button
        ref={ref}
        className={cn(
          'inline-flex items-center justify-center gap-2 rounded-lg font-medium transition-colors',
          'focus:outline-none focus-visible:ring-2 focus-visible:ring-offset-2',
          'disabled:pointer-events-none disabled:opacity-50',
          variantStyles[variant],
          sizeStyles[size],
          className,
        )}
        {...props}
      />
    );
  },
);

Button.displayName = 'Button';
