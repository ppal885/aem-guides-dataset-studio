import { ReactNode } from 'react';
import { cn } from '@/lib/utils';

/** Matches Cursor docs top bar height */
export const APP_HEADER_HEIGHT_PX = 56;

export function AppPageHeader({
  title,
  description,
  children,
  className,
}: {
  title: string;
  description?: string;
  children?: ReactNode;
  className?: string;
}) {
  return (
    <header className={cn('border-b border-border pb-6', className)}>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0 max-w-3xl">
          <h1 className="text-[1.75rem] font-semibold tracking-tight text-foreground">{title}</h1>
          {description ? (
            <p className="mt-2 text-[15px] leading-relaxed text-muted-foreground">{description}</p>
          ) : null}
        </div>
        {children ? <div className="flex shrink-0 items-center gap-2">{children}</div> : null}
      </div>
    </header>
  );
}

export function AppPageShell({
  children,
  className,
  wide,
}: {
  children: ReactNode;
  className?: string;
  /** Use for builder / tables that need more horizontal space */
  wide?: boolean;
}) {
  return (
    <div
      className={cn(
        'mx-auto w-full px-5 py-8 sm:px-6',
        wide ? 'max-w-[1400px]' : 'max-w-5xl',
        className
      )}
    >
      {children}
    </div>
  );
}
