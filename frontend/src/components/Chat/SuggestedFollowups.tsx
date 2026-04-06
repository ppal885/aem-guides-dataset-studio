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
      <span className="self-center text-[11px] font-medium text-slate-400">Try next:</span>
      {followups.map((f, i) => (
        <button
          key={i}
          type="button"
          onClick={() => onSelect(f.text)}
          className="rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-600 shadow-sm transition hover:border-slate-300 hover:bg-slate-50 hover:text-slate-800 active:bg-slate-100"
          title={f.text}
        >
          {f.label}
        </button>
      ))}
    </div>
  );
}
