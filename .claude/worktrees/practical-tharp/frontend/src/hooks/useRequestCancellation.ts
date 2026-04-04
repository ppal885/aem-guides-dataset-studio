import { useEffect, useRef } from 'react';

/**
 * Hook for managing request cancellation with AbortController.
 * Automatically cancels requests when component unmounts or dependencies change.
 * 
 * @returns AbortController instance that is cancelled on unmount
 * 
 * @example
 * ```tsx
 * const abortController = useRequestCancellation();
 * 
 * useEffect(() => {
 *   fetch('/api/data', { signal: abortController.signal })
 *     .then(res => res.json())
 *     .then(data => {
 *       if (!abortController.signal.aborted) {
 *         setData(data);
 *       }
 *     });
 *   
 *   return () => abortController.abort();
 * }, [abortController]);
 * ```
 */
export function useRequestCancellation(): AbortController {
  const abortControllerRef = useRef<AbortController | null>(null);

  useEffect(() => {
    abortControllerRef.current = new AbortController();
    
    return () => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
    };
  }, []);

  if (!abortControllerRef.current) {
    abortControllerRef.current = new AbortController();
  }

  return abortControllerRef.current;
}

/**
 * Hook that creates a new AbortController whenever dependencies change.
 * Useful for cancelling previous requests when inputs change.
 * 
 * @param deps - Dependencies that trigger a new AbortController
 * @returns AbortController instance
 * 
 * @example
 * ```tsx
 * const abortController = useRequestCancellationWithDeps([searchQuery]);
 * 
 * useEffect(() => {
 *   fetch(`/api/search?q=${searchQuery}`, { signal: abortController.signal })
 *     .then(res => res.json())
 *     .then(data => {
 *       if (!abortController.signal.aborted) {
 *         setResults(data);
 *       }
 *     });
 * }, [searchQuery, abortController]);
 * ```
 */
export function useRequestCancellationWithDeps(deps: React.DependencyList): AbortController {
  const abortControllerRef = useRef<AbortController | null>(null);

  useEffect(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    abortControllerRef.current = new AbortController();
    
    return () => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
    };
  }, deps);

  if (!abortControllerRef.current) {
    abortControllerRef.current = new AbortController();
  }

  return abortControllerRef.current;
}
