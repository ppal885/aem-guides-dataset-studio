import { AlertCircle, AlertTriangle } from 'lucide-react';

interface ValidationError {
  field: string;
  message: string;
  severity: 'error' | 'warning';
}

interface ValidationDisplayProps {
  errors: ValidationError[];
  warnings: ValidationError[];
}

export function ValidationDisplay({ errors, warnings }: ValidationDisplayProps) {
  if (errors.length === 0 && warnings.length === 0) {
    return null;
  }

  return (
    <div className="space-y-2">
      {errors.map((error, idx) => (
        <div
          key={`error-${idx}`}
          className="flex items-start gap-2 rounded-md border border-red-500/25 bg-red-500/5 px-3 py-2 text-[12px] text-red-600 dark:text-red-300"
        >
          <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0 opacity-80" />
          <span className="leading-relaxed">{error.message}</span>
        </div>
      ))}
      {warnings.map((warning, idx) => (
        <div
          key={`warn-${idx}`}
          className="flex items-start gap-2 rounded-md border border-amber-500/25 bg-amber-500/5 px-3 py-2 text-[12px] text-amber-700 dark:text-amber-300"
        >
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 opacity-80" />
          <span className="leading-relaxed">{warning.message}</span>
        </div>
      ))}
    </div>
  );
}
