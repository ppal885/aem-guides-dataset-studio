import { FileCode2, ImageIcon, Search } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { ChatMentionItem } from './chatMentionUtils';

interface ChatMentionMenuProps {
  items: ChatMentionItem[];
  activeIndex: number;
  onSelect: (item: ChatMentionItem) => void;
  onHover: (index: number) => void;
  title?: string;
  className?: string;
}

function MentionIcon({ item }: { item: ChatMentionItem }) {
  if (item.type === 'action') {
    return item.id === 'pick-image' ? (
      <ImageIcon className="h-3.5 w-3.5 shrink-0 opacity-70" />
    ) : (
      <FileCode2 className="h-3.5 w-3.5 shrink-0 opacity-70" />
    );
  }
  return <Search className="h-3.5 w-3.5 shrink-0 opacity-70" />;
}

export function ChatMentionMenu({
  items,
  activeIndex,
  onSelect,
  onHover,
  title = 'Add context',
  className,
}: ChatMentionMenuProps) {
  if (items.length === 0) return null;

  return (
    <div
      className={cn(
        'absolute bottom-full left-0 right-0 z-30 mb-2 overflow-hidden rounded-lg border border-border bg-card shadow-lg',
        className
      )}
      role="listbox"
    >
      <p className="border-b border-border/60 px-3 py-1.5 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
        {title}
      </p>
      <ul className="max-h-52 overflow-y-auto py-1">
        {items.map((item, index) => (
          <li key={item.id}>
            <button
              type="button"
              role="option"
              aria-selected={index === activeIndex}
              className={cn(
                'flex w-full items-start gap-2.5 px-3 py-2 text-left transition',
                index === activeIndex ? 'bg-muted text-foreground' : 'text-foreground/90 hover:bg-muted/60'
              )}
              onMouseEnter={() => onHover(index)}
              onMouseDown={(e) => {
                e.preventDefault();
                onSelect(item);
              }}
            >
              <MentionIcon item={item} />
              <span className="min-w-0 flex-1">
                <span className="block text-[12px] font-medium leading-tight">{item.label}</span>
                <span className="mt-0.5 block text-[11px] leading-snug text-muted-foreground">
                  {item.description}
                </span>
              </span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
