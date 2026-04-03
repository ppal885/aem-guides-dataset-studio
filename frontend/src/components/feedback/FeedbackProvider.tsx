import {
  type ReactNode,
  useCallback,
  useMemo,
  useRef,
  useState,
} from 'react';
import { AlertCircle, AlertTriangle, CheckCircle2, Info, X } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import {
  ConfirmOptions,
  FeedbackContext,
  FeedbackContextValue,
  ToastOptions,
} from './feedback-context';

interface ToastEntry extends ToastOptions {
  id: string;
}

interface ConfirmState extends ConfirmOptions {
  open: boolean;
}

const TOAST_STYLES: Record<
  NonNullable<ToastOptions['tone']>,
  { container: string; icon: typeof CheckCircle2 }
> = {
  success: {
    container: 'border-emerald-200 bg-emerald-50 text-emerald-950',
    icon: CheckCircle2,
  },
  error: {
    container: 'border-red-200 bg-red-50 text-red-950',
    icon: AlertCircle,
  },
  info: {
    container: 'border-blue-200 bg-blue-50 text-blue-950',
    icon: Info,
  },
  warning: {
    container: 'border-amber-200 bg-amber-50 text-amber-950',
    icon: AlertTriangle,
  },
};

export function FeedbackProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastEntry[]>([]);
  const [confirmState, setConfirmState] = useState<ConfirmState | null>(null);
  const confirmResolver = useRef<((value: boolean) => void) | null>(null);

  const dismissToast = useCallback((id: string) => {
    setToasts((current) => current.filter((toast) => toast.id !== id));
  }, []);

  const notify = useCallback(
    ({ title, message, tone = 'info', durationMs = 4000 }: ToastOptions) => {
      const id = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
      setToasts((current) => [...current, { id, title, message, tone, durationMs }]);
      window.setTimeout(() => dismissToast(id), durationMs);
    },
    [dismissToast]
  );

  const resolveConfirm = useCallback((value: boolean) => {
    confirmResolver.current?.(value);
    confirmResolver.current = null;
    setConfirmState(null);
  }, []);

  const confirm = useCallback((options: ConfirmOptions) => {
    setConfirmState({ ...options, open: true });
    return new Promise<boolean>((resolve) => {
      confirmResolver.current = resolve;
    });
  }, []);

  const value = useMemo<FeedbackContextValue>(
    () => ({
      notify,
      success: (title, message) => notify({ title, message, tone: 'success' }),
      error: (title, message) => notify({ title, message, tone: 'error' }),
      info: (title, message) => notify({ title, message, tone: 'info' }),
      warning: (title, message) => notify({ title, message, tone: 'warning' }),
      confirm,
    }),
    [confirm, notify]
  );

  return (
    <FeedbackContext.Provider value={value}>
      {children}

      <div className="pointer-events-none fixed right-4 top-4 z-[80] flex w-[min(24rem,calc(100vw-2rem))] flex-col gap-3">
        {toasts.map((toast) => {
          const tone = toast.tone || 'info';
          const Icon = TOAST_STYLES[tone].icon;
          return (
            <div
              key={toast.id}
              className={cn(
                'pointer-events-auto rounded-2xl border p-4 shadow-lg backdrop-blur',
                TOAST_STYLES[tone].container
              )}
              role="status"
              aria-live="polite"
            >
              <div className="flex items-start gap-3">
                <Icon className="mt-0.5 h-4 w-4 shrink-0" />
                <div className="min-w-0 flex-1">
                  <div className="font-semibold">{toast.title}</div>
                  {toast.message ? <div className="mt-1 text-sm opacity-90">{toast.message}</div> : null}
                </div>
                <button
                  type="button"
                  onClick={() => dismissToast(toast.id)}
                  className="rounded-full p-1 opacity-70 transition hover:bg-black/5 hover:opacity-100"
                  aria-label="Dismiss notification"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
            </div>
          );
        })}
      </div>

      {confirmState?.open ? (
        <div className="fixed inset-0 z-[90] flex items-center justify-center bg-slate-950/45 px-4 py-8 backdrop-blur-sm">
          <div
            className="w-full max-w-md rounded-3xl border border-slate-200 bg-white p-6 shadow-2xl"
            role="dialog"
            aria-modal="true"
            aria-labelledby="app-confirm-title"
            aria-describedby="app-confirm-message"
          >
            <div className="flex items-start gap-3">
              <div
                className={cn(
                  'flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl',
                  confirmState.tone === 'danger' ? 'bg-red-50 text-red-600' : 'bg-blue-50 text-blue-600'
                )}
              >
                {confirmState.tone === 'danger' ? (
                  <AlertTriangle className="h-5 w-5" />
                ) : (
                  <Info className="h-5 w-5" />
                )}
              </div>
              <div className="min-w-0">
                <h2 id="app-confirm-title" className="text-lg font-semibold text-slate-950">
                  {confirmState.title}
                </h2>
                <p id="app-confirm-message" className="mt-2 text-sm leading-6 text-slate-600">
                  {confirmState.message}
                </p>
              </div>
            </div>
            <div className="mt-6 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
              <Button variant="outline" onClick={() => resolveConfirm(false)}>
                {confirmState.cancelLabel || 'Cancel'}
              </Button>
              <Button
                onClick={() => resolveConfirm(true)}
                className={cn(
                  confirmState.tone === 'danger'
                    ? 'bg-red-600 text-white hover:bg-red-700'
                    : 'bg-blue-600 text-white hover:bg-blue-700'
                )}
              >
                {confirmState.confirmLabel || 'Continue'}
              </Button>
            </div>
          </div>
        </div>
      ) : null}
    </FeedbackContext.Provider>
  );
}
