import { describe, expect, it } from 'vitest';

import {
  getToolCatalogEmptyStateMessage,
  getToolCatalogHelperText,
  shouldRetryToolCatalog,
} from './toolCatalogStateUtils';

describe('toolCatalogStateUtils', () => {
  it('retries when the catalog has not loaded yet or is in error', () => {
    expect(shouldRetryToolCatalog('idle')).toBe(true);
    expect(shouldRetryToolCatalog('error')).toBe(true);
    expect(shouldRetryToolCatalog('loading')).toBe(false);
    expect(shouldRetryToolCatalog('ready')).toBe(false);
  });

  it('distinguishes backend-unreachable helper text from catalog fetch errors', () => {
    expect(
      getToolCatalogHelperText({
        status: 'error',
        backendReachable: false,
        toolsCount: 0,
      })
    ).toContain('backend is unreachable');

    expect(
      getToolCatalogHelperText({
        status: 'error',
        backendReachable: true,
        toolsCount: 0,
      })
    ).toContain('could not be loaded');
  });

  it('keeps no-match empty state separate from catalog failure', () => {
    expect(
      getToolCatalogEmptyStateMessage({
        status: 'ready',
        backendReachable: true,
        toolsCount: 3,
        slashQuery: 'native-pdf-foo',
      })
    ).toBe('No tools match "native-pdf-foo".');
  });

  it('surfaces the catalog error when no tools are loaded', () => {
    expect(
      getToolCatalogEmptyStateMessage({
        status: 'error',
        backendReachable: true,
        toolsCount: 0,
        errorMessage: 'Temporary 502 from the proxy.',
      })
    ).toContain('Temporary 502 from the proxy.');
  });
});
