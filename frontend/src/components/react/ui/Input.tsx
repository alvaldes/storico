import { forwardRef, type InputHTMLAttributes } from 'react';
import { cn } from '@/lib/utils';

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  error?: string;
}

const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ className, error, type, ...props }, ref) => {
    return (
      <div className="flex flex-col gap-1">
        <input
          type={type}
          ref={ref}
          className={cn(
            'flex h-10 w-full rounded-lg border border-(--color-border) bg-(--color-surface) px-3 py-2 text-sm text-(--color-text)',
            'placeholder:text-(--color-text-secondary)',
            'focus:outline-none focus:ring-2 focus:ring-(--color-primary-500) focus:ring-offset-1',
            'disabled:cursor-not-allowed disabled:opacity-50',
            error && 'border-red-500 focus:ring-red-500',
            className,
          )}
          {...props}
        />
        {error && (
          <span className="text-xs text-red-500">{error}</span>
        )}
      </div>
    );
  },
);
Input.displayName = 'Input';

export { Input };
