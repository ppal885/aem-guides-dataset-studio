export type ChatToolsStatus = 'idle' | 'loading' | 'ready' | 'error';

interface ToolCatalogMessageArgs {
  status: ChatToolsStatus;
  backendReachable: boolean | null;
  toolsCount: number;
  slashQuery?: string;
  errorMessage?: string | null;
}

export function shouldRetryToolCatalog(status: ChatToolsStatus): boolean {
  return status === 'idle' || status === 'error';
}

export function getToolCatalogHelperText({
  status,
  backendReachable,
  toolsCount,
}: ToolCatalogMessageArgs): string {
  if (status === 'loading' && toolsCount === 0) {
    return 'Loading slash tools from the backend catalog.';
  }
  if (status !== 'error') {
    return '';
  }
  if (backendReachable === false) {
    return 'Slash tools are unavailable because the backend is unreachable right now.';
  }
  return 'Slash tools could not be loaded just now. Open the slash palette again or retry tools.';
}

export function getToolCatalogEmptyStateMessage({
  status,
  backendReachable,
  toolsCount,
  slashQuery,
  errorMessage,
}: ToolCatalogMessageArgs): string {
  if (status === 'loading' && toolsCount === 0) {
    return 'Loading slash tools…';
  }
  if (status === 'error' && toolsCount === 0) {
    if (backendReachable === false) {
      return 'The backend is unreachable, so slash tools cannot be loaded right now.';
    }
    if (errorMessage?.trim()) {
      return `The tool catalog could not be loaded. ${errorMessage.trim()}`;
    }
    return 'The tool catalog could not be loaded right now. Try again in a moment.';
  }
  if (slashQuery?.trim()) {
    return `No tools match "${slashQuery}".`;
  }
  return 'No chat tools are currently available.';
}
