/**
 * Request deduplication utility to prevent duplicate API calls.
 * Caches in-flight requests and returns the same promise for identical requests.
 */

interface CachedRequest {
  promise: Promise<Response>;
  timestamp: number;
}

const requestCache = new Map<string, CachedRequest>();
const DEFAULT_TTL = 5000; // 5 seconds

/**
 * Create a request key from URL, method, and body.
 */
function createRequestKey(
  url: string,
  method: string = 'GET',
  body?: BodyInit | null
): string {
  const bodyHash = body
    ? typeof body === 'string'
      ? body
      : JSON.stringify(body)
    : '';
  return `${method}:${url}:${bodyHash}`;
}

/**
 * Clean up expired cache entries.
 */
function cleanupCache(ttl: number = DEFAULT_TTL): void {
  const now = Date.now();
  const expiredKeys: string[] = [];

  requestCache.forEach((cached, key) => {
    if (now - cached.timestamp > ttl) {
      expiredKeys.push(key);
    }
  });

  expiredKeys.forEach(key => requestCache.delete(key));
}

/**
 * Fetch with request deduplication.
 * If an identical request is already in flight, returns the same promise.
 * 
 * @param url - The URL to fetch
 * @param options - Fetch options
 * @param ttl - Time-to-live for cached requests in milliseconds (default: 5000)
 * @returns Promise resolving to Response
 * 
 * @example
 * ```ts
 * // Multiple calls with same parameters will share the same promise
 * const promise1 = deduplicatedFetch('/api/data', { method: 'POST', body: 'test' });
 * const promise2 = deduplicatedFetch('/api/data', { method: 'POST', body: 'test' });
 * // promise1 === promise2 (same promise instance)
 * ```
 */
export function deduplicatedFetch(
  url: string,
  options: RequestInit = {},
  ttl: number = DEFAULT_TTL
): Promise<Response> {
  const key = createRequestKey(url, options.method || 'GET', options.body);
  
  // Clean up expired entries periodically
  if (Math.random() < 0.1) {
    cleanupCache(ttl);
  }

  // Check if request is already in flight
  const cached = requestCache.get(key);
  if (cached && Date.now() - cached.timestamp < ttl) {
    return cached.promise;
  }

  // Create new request
  const promise = fetch(url, options).finally(() => {
    // Remove from cache after request completes (success or failure)
    setTimeout(() => {
      requestCache.delete(key);
    }, ttl);
  });

  // Cache the promise
  requestCache.set(key, {
    promise,
    timestamp: Date.now(),
  });

  return promise;
}

/**
 * Fetch JSON with request deduplication.
 * 
 * @param url - The URL to fetch
 * @param options - Fetch options
 * @param ttl - Time-to-live for cached requests in milliseconds
 * @returns Promise resolving to parsed JSON data
 */
export async function deduplicatedFetchJson<T = any>(
  url: string,
  options: RequestInit = {},
  ttl: number = DEFAULT_TTL
): Promise<T> {
  const response = await deduplicatedFetch(url, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
  }, ttl);

  if (!response.ok) {
    const errorText = await response.text().catch(() => 'Unknown error');
    throw new Error(`HTTP ${response.status}: ${errorText}`);
  }

  return response.json();
}

/**
 * Clear all cached requests.
 */
export function clearRequestCache(): void {
  requestCache.clear();
}

/**
 * Get the number of cached requests.
 */
export function getCacheSize(): number {
  return requestCache.size;
}
