import { AlertCircle, AlertTriangle, CheckCircle2 } from 'lucide-react';

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
    return (
      <div className="p-4 bg-gradient-to-r from-green-50 to-emerald-50 border border-green-200 rounded-lg">
        <div className="flex items-center gap-3">
          <div className="p-1.5 bg-green-100 rounded-md">
            <CheckCircle2 className="w-4 h-4 text-green-600" />
          </div>
          <span className="text-sm font-semibold text-green-700">All validations passed</span>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {errors.length > 0 && (
        <div className="p-4 bg-gradient-to-r from-red-50 to-rose-50 border border-red-200 rounded-lg animate-in slide-in-from-top-2 duration-200">
          <div className="flex items-start gap-3">
            <div className="p-1.5 bg-red-100 rounded-md flex-shrink-0 mt-0.5">
              <AlertCircle className="w-4 h-4 text-red-600" />
            </div>
            <div className="flex-1">
              <h4 className="font-semibold text-red-800 mb-2.5 text-sm">Validation Errors</h4>
              <ul className="space-y-2">
                {errors.map((error, idx) => (
                  <li key={idx} className="text-sm text-red-700 flex items-start gap-2">
                    <span className="text-red-500 mt-1.5 font-bold">•</span>
                    <span className="leading-relaxed">{error.message}</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      )}
      {warnings.length > 0 && (
        <div className="p-4 bg-gradient-to-r from-yellow-50 to-amber-50 border border-yellow-200 rounded-lg animate-in slide-in-from-top-2 duration-200">
          <div className="flex items-start gap-3">
            <div className="p-1.5 bg-yellow-100 rounded-md flex-shrink-0 mt-0.5">
              <AlertTriangle className="w-4 h-4 text-yellow-600" />
            </div>
            <div className="flex-1">
              <h4 className="font-semibold text-yellow-800 mb-2.5 text-sm">Warnings</h4>
              <ul className="space-y-2">
                {warnings.map((warning, idx) => (
                  <li key={idx} className="text-sm text-yellow-700 flex items-start gap-2">
                    <span className="text-yellow-500 mt-1.5 font-bold">•</span>
                    <span className="leading-relaxed">{warning.message}</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
