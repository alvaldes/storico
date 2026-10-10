'use client';

import { useEffect, useRef, useState } from 'react';
import { Check, Copy } from 'lucide-react';
import { Button } from '@/components/ui/button';

/**
 * Write text to the clipboard, reporting whether it happened.
 *
 * The clipboard API is not available in every context (insecure origins,
 * missing permissions, jsdom), so a copy that cannot happen is a quiet `false`
 * the caller decides about — the text stays readable either way, never lost.
 */
export async function copyToClipboard(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    return false;
  }
}

interface CopyButtonProps {
  /** The text the button writes, verbatim. */
  text: string;
  /** Accessible name while nothing has been copied yet. */
  label: string;
  /** Accessible name in the copied state. */
  copiedLabel: string;
  className?: string;
  /** Disable the button — nothing to copy yet. */
  disabled?: boolean;
  /** How long the copied state stays before reverting (ms). */
  copiedResetMs?: number;
}

/**
 * The shared copy affordance: one icon button that writes its `text` to the
 * clipboard and announces the copied state through its accessible name.
 *
 * It was born when the export page's preview needed the repository's first
 * copy helper — until then the only `navigator.clipboard` call lived inside
 * `ErrorDisplay`'s raw-response disclosure — and `ErrorDisplay` now rides it
 * too: same button shape, same icon pair, same 2 s reset.
 */
export function CopyButton({
  text,
  label,
  copiedLabel,
  className,
  disabled,
  copiedResetMs = 2000,
}: CopyButtonProps) {
  const [copied, setCopied] = useState(false);
  const resetTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // The reset timer must not fire into an unmounted button.
  useEffect(
    () => () => {
      if (resetTimer.current) clearTimeout(resetTimer.current);
    },
    [],
  );

  const handleCopy = async () => {
    const copiedOk = await copyToClipboard(text);
    if (!copiedOk) return; // the state only turns when the write happened
    setCopied(true);
    if (resetTimer.current) clearTimeout(resetTimer.current);
    resetTimer.current = setTimeout(() => setCopied(false), copiedResetMs);
  };

  return (
    <Button
      variant="ghost"
      size="icon"
      onClick={handleCopy}
      aria-label={copied ? copiedLabel : label}
      className={className}
      disabled={disabled}
    >
      {copied ? (
        <Check className="h-3.5 w-3.5 text-(--color-success)" />
      ) : (
        <Copy className="h-3.5 w-3.5" />
      )}
    </Button>
  );
}
