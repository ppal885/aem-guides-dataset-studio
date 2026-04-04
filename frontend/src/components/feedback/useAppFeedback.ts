import { useContext } from 'react';

import { FeedbackContext } from './feedback-context';

export function useAppFeedback() {
  const context = useContext(FeedbackContext);
  if (!context) {
    throw new Error('useAppFeedback must be used within FeedbackProvider');
  }
  return context;
}
