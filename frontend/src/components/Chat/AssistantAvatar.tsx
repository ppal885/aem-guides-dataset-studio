import { Sparkles } from 'lucide-react';
import { cn } from '@/lib/utils';

type AssistantAvatarSize = 'sm' | 'md' | 'lg';

const sizeClasses: Record<AssistantAvatarSize, string> = {
  sm: 'h-7 w-7 rounded-md',
  md: 'h-9 w-9 rounded-lg',
  lg: 'h-12 w-12 rounded-xl',
};

const iconClasses: Record<AssistantAvatarSize, string> = {
  sm: 'h-3.5 w-3.5',
  md: 'h-4 w-4',
  lg: 'h-6 w-6',
};

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
        'flex shrink-0 items-center justify-center bg-foreground text-background',
        sizeClasses[size],
        className
      )}
      aria-hidden
    >
      <Sparkles className={iconClasses[size]} strokeWidth={2.25} />
    </div>
  );
}
