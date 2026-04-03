import { createContext, type ReactNode } from 'react';

type FeedbackTone = 'success' | 'error' | 'info' | 'warning';

export interface ToastOptions {
  title: string;
  message?: string | ReactNode;
  tone?: FeedbackTone;
  durationMs?: number;
}

export interface ConfirmOptions {
  title: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  tone?: 'default' | 'danger';
}

export interface FeedbackContextValue {
  notify: (options: ToastOptions) => void;
  success: (title: string, message?: string | ReactNode) => void;
  error: (title: string, message?: string | ReactNode) => void;
  info: (title: string, message?: string | ReactNode) => void;
  warning: (title: string, message?: string | ReactNode) => void;
  confirm: (options: ConfirmOptions) => Promise<boolean>;
}

export const FeedbackContext = createContext<FeedbackContextValue | null>(null);
