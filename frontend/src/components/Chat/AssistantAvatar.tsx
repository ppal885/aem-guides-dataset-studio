import { Sparkles } from 'lucide-react';
import { cn } from '@/lib/utils';

type AssistantAvatarSize = 'md' | 'lg';

const sizeClasses: Record<AssistantAvatarSize, string> = {
  md: 'h-10 w-10',
  lg: 'h-14 w-14',
};

const iconClasses: Record<AssistantAvatarSize, string> = {
  md: 'h-5 w-5',
  lg: 'h-7 w-7',
};

/**
 * Distinct assistant mark for chat — avoids generic “robot” silhouette; reads as AI / guidance.
 */
export function AssistantAvatar({
  className,
  size = 'md',
}: {
  className?: string;
  size?: AssistantAvatarSize;
}) {
  return (
    <div
      className={cn(
        'relative flex shrink-0 items-center justify-center overflow-hidden rounded-2xl shadow-md ring-2 ring-white',
        'bg-gradient-to-br from-teal-600 via-teal-700 to-slate-700 text-white',
        'shadow-teal-900/25',
        sizeClasses[size],
        className
      )}
      aria-hidden
    >
      <div
        className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_30%_20%,rgba(255,255,255,0.35),transparent_55%)]"
        aria-hidden
      />
      <div
        className="pointer-events-none absolute -right-1 -top-1 h-6 w-6 rounded-full bg-white/15 blur-md"
        aria-hidden
      />
      <Sparkles
        className={cn('relative drop-shadow-sm', iconClasses[size])}
        strokeWidth={2.25}
      />
    </div>
  );
}
