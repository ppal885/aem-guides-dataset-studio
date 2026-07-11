import type { SuggestedFollowup } from '@/api/chat';

interface SuggestedFollowupsProps {
  followups: SuggestedFollowup[];
  onSelect: (text: string) => void;
  className?: string;
}

export function SuggestedFollowups({ followups, onSelect, className }: SuggestedFollowupsProps) {
  if (!followups.length) return null;

  return (
    <div className={`flex flex-wrap gap-2 ${className ?? ''}`}>
      <span className="self-center text-[11px] font-medium text-muted-foreground">Try next:</span>
      {followups.map((f, i) => (
        <button
          key={i}
          type="button"
          onClick={() => onSelect(f.text)}
          className="rounded-full border border-border bg-card px-3 py-1.5 text-xs font-medium text-muted-foreground transition hover:bg-muted hover:text-foreground"
          title={f.text}
        >
          {f.label}
        </button>
      ))}
    </div>
  );
}
