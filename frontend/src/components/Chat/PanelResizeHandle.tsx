import { cn } from '@/lib/utils';

interface PanelResizeHandleProps {
  side: 'left' | 'right';
  dragging?: boolean;
  onMouseDown: (e: React.MouseEvent) => void;
  onDoubleClick?: () => void;
  className?: string;
  title?: string;
}

export function PanelResizeHandle({
  side,
  dragging = false,
  onMouseDown,
  onDoubleClick,
  className,
  title = 'Drag to resize',
}: PanelResizeHandleProps) {
  return (
    <div
      role="separator"
      aria-orientation="vertical"
      aria-label={title}
      title={onDoubleClick ? `${title} · double-click to reset` : title}
      onMouseDown={onMouseDown}
      onDoubleClick={onDoubleClick}
      className={cn(
        'panel-resize-handle absolute top-0 bottom-0 z-20 cursor-col-resize',
        side === 'right' ? 'right-0' : 'left-0',
        dragging && 'panel-resize-handle-active',
        className
      )}
    />
  );
}
