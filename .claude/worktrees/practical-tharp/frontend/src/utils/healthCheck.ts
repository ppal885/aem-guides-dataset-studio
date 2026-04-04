/**
 * Health check utility with retry logic for backend connectivity.
 */

import { fetchWithRetry, RetryOptions } from './api';

export interface HealthStatus {
  status: 'healthy' | 'unhealthy' | 'unknown';
  timestamp: number;
  responseTime?: number;
  error?: string;
}

const DEFAULT_RETRY_OPTIONS: RetryOptions = {
  maxAttempts: 3,
  baseDelay: 1000,
  maxDelay: 5000,
  retryableStatuses: [408, 429, 500, 502, 503, 504],
  retryableErrors: ['NetworkError', 'Failed to fetch', 'timeout'],
};

/**
 * Check backend health status with retry logic.
 * 
 * @param endpoint - Health check endpoint URL (default: '/health')
 * @param retryOptions - Retry configuration options
 * @returns Promise resolving to HealthStatus
 * 
 * @example
 * ```ts
 * const health = await checkBackendHealth();
 * if (health.status === 'healthy') {
 *   console.log('Backend is ready');
 * }
 * ```
 */
export async function checkBackendHealth(
  endpoint: string = '/health',
  retryOptions: RetryOptions = {}
): Promise<HealthStatus> {
  const startTime = Date.now();
  const opts = { ...DEFAULT_RETRY_OPTIONS, ...retryOptions };

  try {
    const response = await fetchWithRetry(endpoint, {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
      },
    }, opts);

    const responseTime = Date.now() - startTime;

    if (response.ok) {
      const data = await response.json().catch(() => ({}));
      
      return {
        status: data.status === 'healthy' ? 'healthy' : 'unhealthy',
        timestamp: Date.now(),
        responseTime,
      };
    }

    return {
      status: 'unhealthy',
      timestamp: Date.now(),
      responseTime,
      error: `HTTP ${response.status}`,
    };
  } catch (error) {
    const responseTime = Date.now() - startTime;
    const errorMessage = error instanceof Error ? error.message : String(error);

    return {
      status: 'unhealthy',
      timestamp: Date.now(),
      responseTime,
      error: errorMessage,
    };
  }
}

/**
 * Wait for backend to become healthy with polling.
 * 
 * @param endpoint - Health check endpoint URL
 * @param maxAttempts - Maximum number of health check attempts
 * @param interval - Interval between checks in milliseconds
 * @param retryOptions - Retry configuration for each health check
 * @returns Promise resolving to HealthStatus when healthy, or rejecting if max attempts reached
 * 
 * @example
 * ```ts
 * try {
 *   await waitForBackendHealth('/health', 10, 2000);
 *   console.log('Backend is ready!');
 * } catch (error) {
 *   console.error('Backend failed to become healthy');
 * }
 * ```
 */
export async function waitForBackendHealth(
  endpoint: string = '/health',
  maxAttempts: number = 10,
  interval: number = 2000,
  retryOptions: RetryOptions = {}
): Promise<HealthStatus> {
  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    const health = await checkBackendHealth(endpoint, retryOptions);

    if (health.status === 'healthy') {
      return health;
    }

    if (attempt < maxAttempts) {
      await new Promise(resolve => setTimeout(resolve, interval));
    }
  }

  throw new Error(
    `Backend failed to become healthy after ${maxAttempts} attempts`
  );
}

/**
 * Check if backend is healthy before performing a critical operation.
 * 
 * @param operation - Function to execute if backend is healthy
 * @param endpoint - Health check endpoint URL
 * @param retryOptions - Retry configuration options
 * @returns Promise resolving to operation result
 * 
 * @example
 * ```ts
 * const result = await ensureBackendHealth(async () => {
 *   return await createJob(jobData);
 * });
 * ```
 */
export async function ensureBackendHealth<T>(
  operation: () => Promise<T>,
  endpoint: string = '/health',
  retryOptions: RetryOptions = {}
): Promise<T> {
  const health = await checkBackendHealth(endpoint, retryOptions);

  if (health.status !== 'healthy') {
    throw new Error(
      `Backend is not healthy: ${health.error || 'Unknown error'}`
    );
  }

  return operation();
}

/**
 * Monitor backend health periodically.
 * 
 * @param callback - Function called with health status on each check
 * @param endpoint - Health check endpoint URL
 * @param interval - Interval between checks in milliseconds
 * @param retryOptions - Retry configuration options
 * @returns Function to stop monitoring
 * 
 * @example
 * ```ts
 * const stopMonitoring = monitorBackendHealth((health) => {
 *   console.log('Backend status:', health.status);
 * }, '/health', 5000);
 * 
 * // Later, stop monitoring
 * stopMonitoring();
 * ```
 */
export function monitorBackendHealth(
  callback: (health: HealthStatus) => void,
  endpoint: string = '/health',
  interval: number = 5000,
  retryOptions: RetryOptions = {}
): () => void {
  let isRunning = true;

  const checkHealth = async () => {
    if (!isRunning) {
      return;
    }

    try {
      const health = await checkBackendHealth(endpoint, retryOptions);
      callback(health);
    } catch (error) {
      callback({
        status: 'unknown',
        timestamp: Date.now(),
        error: error instanceof Error ? error.message : String(error),
      });
    }

    if (isRunning) {
      setTimeout(checkHealth, interval);
    }
  };

  checkHealth();

  return () => {
    isRunning = false;
  };
}
