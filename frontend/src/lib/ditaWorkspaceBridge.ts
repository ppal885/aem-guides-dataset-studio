/**
 * Session handoff: queue a generated DITA topic for the workspace / editor (sessionStorage).
 */
export const DITA_WORKSPACE_STORAGE_KEY = 'aem-studio:dita-workspace-pending-topic';

export interface PendingWorkspaceTopicPayload {
  xml: string;
  filename: string;
  title: string;
  ditaType: string;
  validationValid: boolean;
  blockingIssues: string[];
  warnings: string[];
  mode: 'new_topic' | 'replace_draft' | string;
}

export function enqueueGeneratedTopicForWorkspace(payload: PendingWorkspaceTopicPayload): void {
  try {
    sessionStorage.setItem(DITA_WORKSPACE_STORAGE_KEY, JSON.stringify(payload));
  } catch {
    /* ignore quota / private mode */
  }
}

export function peekPendingWorkspaceTopic(): PendingWorkspaceTopicPayload | null {
  try {
    const raw = sessionStorage.getItem(DITA_WORKSPACE_STORAGE_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as PendingWorkspaceTopicPayload;
  } catch {
    return null;
  }
}

export function consumePendingWorkspaceTopic(): PendingWorkspaceTopicPayload | null {
  const payload = peekPendingWorkspaceTopic();
  try {
    sessionStorage.removeItem(DITA_WORKSPACE_STORAGE_KEY);
  } catch {
    /* ignore */
  }
  return payload;
}

export function clearPendingWorkspaceTopic(): void {
  try {
    sessionStorage.removeItem(DITA_WORKSPACE_STORAGE_KEY);
  } catch {
    /* ignore */
  }
}
