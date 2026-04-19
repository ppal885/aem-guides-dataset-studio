import { AlertTriangle } from 'lucide-react';

interface ApprovalGateProps {
  message: string;
  tools: string[];
  className?: string;
}

export function ApprovalGate({ message, tools, className }: ApprovalGateProps) {
  return (
    <div
      className={`rounded-xl border-2 border-amber-300 bg-amber-50/80 p-4 shadow-sm ${className ?? ''}`}
    >
      <div className="flex items-start gap-3">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-amber-500 text-white shadow-sm">
          <AlertTriangle className="h-4.5 w-4.5" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="text-sm font-semibold text-amber-900">Approval Required</div>
          <p className="mt-1 text-sm leading-relaxed text-amber-800">{message}</p>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {tools.map((t) => (
              <span
                key={t}
                className="rounded-full border border-amber-200 bg-white px-2.5 py-0.5 text-[11px] font-medium text-amber-700"
              >
                {t}
              </span>
            ))}
          </div>
          <p className="mt-2.5 text-xs text-amber-700/80">
            Type <strong>&quot;yes&quot;</strong> or <strong>&quot;confirm&quot;</strong> to proceed, or
            describe how you&apos;d like to adjust the request.
          </p>
        </div>
      </div>
    </div>
  );
}
