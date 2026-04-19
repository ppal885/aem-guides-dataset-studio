/**
 * API utility functions with retry logic and error handling.
 */

/** Base URL for API calls. Empty = relative (uses Vite proxy in dev). Set VITE_API_BASE_URL for direct backend. */
function normalizeApiBase(raw: string): string {
  const s = (raw || '').trim();
  if (!s) return '';
  if (s.startsWith('http://') || s.startsWith('https://')) return s.replace(/\/$/, '');
  return `http://${s.replace(/\/$/, '')}`;
}

function inferLocalDevApiBase(): string {
  if (typeof window === 'undefined') return '';
  const host = window.location.hostname.toLowerCase();
  if (host === 'localhost' || host === '127.0.0.1' || host === '::1' || host === '[::1]') {
    return 'http://127.0.0.1:8001';
  }
  return '';
}

const API_BASE =
  normalizeApiBase(import.meta.env.VITE_API_BASE_URL as string) || inferLocalDevApiBase();

export function apiUrl(path: string): string {
  const base = API_BASE;
  const p = path.startsWith('/') ? path : `/${path}`;
  return base ? `${base}${p}` : p;
}

export function canonicalJobsRouteErrorMessage(error: unknown): string {
  const raw = error instanceof Error ? error.message : String(error ?? 'Unknown error');
  if (/not found/i.test(raw) || /\b404\b/.test(raw)) {
    return 'The canonical jobs API was not found on the backend. This usually means the frontend is pointing at the wrong backend instance or the jobs router is missing.';
  }
  if (/failed to fetch|networkerror|network request failed/i.test(raw)) {
    return 'The backend could not be reached. Check that the API server is running and that the frontend is pointed at the correct backend URL.';
  }
  if (/401|403|unauthorized|forbidden|access denied/i.test(raw)) {
    return 'The backend rejected the request due to authentication or authorization. Please sign in again or verify your access.';
  }
  return raw;
}

export interface RetryOptions {
  maxAttempts?: number;
  baseDelay?: number;
  maxDelay?: number;
  retryableStatuses?: number[];
  retryableErrors?: string[];
}

const DEFAULT_RETRY_OPTIONS: Required<RetryOptions> = {
  maxAttempts: 3,
  baseDelay: 1000,
  maxDelay: 10000,
  retryableStatuses: [408, 429, 500, 502, 503, 504],
  retryableErrors: ['NetworkError', 'Failed to fetch', 'timeout'],
};

/**
 * Sleep for specified milliseconds.
 */
function sleep(ms: number): Promise<void> {
  return new Promise(resolve => setTimeout(resolve, ms));
}

/**
 * Calculate exponential backoff delay.
 */
function calculateBackoff(attempt: number, baseDelay: number, maxDelay: number): number {
  const delay = baseDelay * Math.pow(2, attempt);
  return Math.min(delay, maxDelay);
}

/**
 * Check if an error is retryable.
 */
function isRetryableError(error: Error, retryableErrors: string[]): boolean {
  const errorMessage = error.message.toLowerCase();
  return retryableErrors.some(retryable => errorMessage.includes(retryable.toLowerCase()));
}

/**
 * Check if a status code is retryable.
 */
function isRetryableStatus(status: number, retryableStatuses: number[]): boolean {
  return retryableStatuses.includes(status);
}

/**
 * Fetch with automatic retry logic and exponential backoff.
 * 
 * @param url - The URL to fetch
 * @param options - Fetch options (same as native fetch)
 * @param retryOptions - Retry configuration options
 * @returns Promise resolving to Response
 * 
 * @example
 * ```ts
 * const response = await fetchWithRetry('/api/data', {
 *   method: 'POST',
 *   body: JSON.stringify({ data: 'test' })
 * }, {
 *   maxAttempts: 5,
 *   baseDelay: 500
 * });
 * ```
 */
export async function fetchWithRetry(
  url: string,
  options: RequestInit = {},
  retryOptions: RetryOptions = {}
): Promise<Response> {
  const opts = { ...DEFAULT_RETRY_OPTIONS, ...retryOptions };
  let lastError: Error | null = null;
  let lastResponse: Response | null = null;

  const fullUrl = url.startsWith('http') ? url : apiUrl(url);
  for (let attempt = 0; attempt < opts.maxAttempts; attempt++) {
    try {
      const response = await fetch(fullUrl, options);
      
      // If response is successful or not retryable, return it
      if (response.ok || !isRetryableStatus(response.status, opts.retryableStatuses)) {
        return response;
      }

      lastResponse = response;

      // If this is the last attempt, return the response
      if (attempt === opts.maxAttempts - 1) {
        return response;
      }

      // Calculate backoff delay
      const delay = calculateBackoff(attempt, opts.baseDelay, opts.maxDelay);
      console.warn(
        `Request failed with status ${response.status}, retrying in ${delay}ms (attempt ${attempt + 1}/${opts.maxAttempts})`
      );
      await sleep(delay);
    } catch (error) {
      lastError = error instanceof Error ? error : new Error(String(error));

      // If error is not retryable, throw immediately
      if (!isRetryableError(lastError, opts.retryableErrors)) {
        throw lastError;
      }

      // If this is the last attempt, throw the error
      if (attempt === opts.maxAttempts - 1) {
        throw lastError;
      }

      // Calculate backoff delay
      const delay = calculateBackoff(attempt, opts.baseDelay, opts.maxDelay);
      console.warn(
        `Request failed with error: ${lastError.message}, retrying in ${delay}ms (attempt ${attempt + 1}/${opts.maxAttempts})`
      );
      await sleep(delay);
    }
  }

  // This should never be reached, but TypeScript needs it
  if (lastError) {
    throw lastError;
  }
  if (lastResponse) {
    return lastResponse;
  }
  throw new Error('Request failed after all retry attempts');
}

/**
 * Fetch JSON with automatic retry logic.
 * 
 * @param url - The URL to fetch
 * @param options - Fetch options
 * @param retryOptions - Retry configuration options
 * @returns Promise resolving to parsed JSON data
 */
export async function fetchJson<T = any>(
  url: string,
  options: RequestInit = {},
  retryOptions: RetryOptions = {}
): Promise<T> {
  // Only set JSON Content-Type when there is a body. Sending Content-Type: application/json on
  // DELETE/GET with no body triggers extra CORS preflights and confuses some proxies; it also
  // matches curl/browsers that omit Content-Type for bodyless DELETE (e.g. clear all chat sessions).
  const hasBody =
    options.body !== undefined &&
    options.body !== null &&
    !(typeof options.body === 'string' && options.body === '');
  const defaultHeaders: Record<string, string> = {};
  if (hasBody) {
    defaultHeaders['Content-Type'] = 'application/json';
  }
  const response = await fetchWithRetry(url, {
    ...options,
    headers: {
      ...defaultHeaders,
      ...(options.headers as Record<string, string>),
    },
  }, retryOptions);

  if (!response.ok) {
    const errorText = await response.text().catch(() => 'Unknown error');
    let message = errorText;
    try {
      const parsed = JSON.parse(errorText);
      if (parsed && typeof parsed.detail === 'string') {
        message = parsed.detail;
      } else if (parsed && Array.isArray(parsed.detail)) {
        message = parsed.detail.map((d: unknown) =>
          typeof d === 'object' && d && 'msg' in d ? (d as { msg: string }).msg : String(d)
        ).join('; ');
      }
    } catch {
      /* use raw errorText */
    }
    throw new Error(message);
  }

  return response.json();
}

/**
 * Fetch with AbortController support and retry logic.
 * 
 * @param url - The URL to fetch
 * @param options - Fetch options (can include signal)
 * @param retryOptions - Retry configuration options
 * @returns Promise resolving to Response
 */
export async function fetchWithAbort(
  url: string,
  options: RequestInit & { signal?: AbortSignal } = {},
  retryOptions: RetryOptions = {}
): Promise<Response> {
  // If signal is already aborted, throw immediately
  if (options.signal?.aborted) {
    throw new DOMException('Request aborted', 'AbortError');
  }

  try {
    return await fetchWithRetry(url, options, retryOptions);
  } catch (error) {
    // If abort was requested, throw AbortError
    if (options.signal?.aborted) {
      throw new DOMException('Request aborted', 'AbortError');
    }
    throw error;
  }
}
