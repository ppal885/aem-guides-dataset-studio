import { describe, expect, it, beforeEach } from 'vitest';
import {
  clearPendingWorkspaceTopic,
  consumePendingWorkspaceTopic,
  DITA_WORKSPACE_STORAGE_KEY,
  enqueueGeneratedTopicForWorkspace,
  peekPendingWorkspaceTopic,
} from './ditaWorkspaceBridge';

describe('ditaWorkspaceBridge', () => {
  beforeEach(() => {
    sessionStorage.clear();
  });

  it('enqueue and peek round-trip', () => {
    enqueueGeneratedTopicForWorkspace({
      xml: '<task id="a"/>',
      filename: 't.dita',
      title: 'T',
      ditaType: 'task',
      validationValid: true,
      blockingIssues: [],
      warnings: ['one'],
      mode: 'new_topic',
    });
    const p = peekPendingWorkspaceTopic();
    expect(p?.xml).toBe('<task id="a"/>');
    expect(p?.warnings).toEqual(['one']);
    expect(p?.mode).toBe('new_topic');
  });

  it('consume removes storage', () => {
    enqueueGeneratedTopicForWorkspace({
      xml: 'x',
      filename: 'f.dita',
      title: 'F',
      ditaType: 'topic',
      validationValid: false,
      blockingIssues: ['bad'],
      warnings: [],
      mode: 'replace_draft',
    });
    expect(consumePendingWorkspaceTopic()).not.toBeNull();
    expect(sessionStorage.getItem(DITA_WORKSPACE_STORAGE_KEY)).toBeNull();
    expect(peekPendingWorkspaceTopic()).toBeNull();
  });

  it('clearPendingWorkspaceTopic', () => {
    enqueueGeneratedTopicForWorkspace({
      xml: 'x',
      filename: 'f.dita',
      title: 'F',
      ditaType: 'topic',
      validationValid: true,
      blockingIssues: [],
      warnings: [],
      mode: 'new_topic',
    });
    clearPendingWorkspaceTopic();
    expect(peekPendingWorkspaceTopic()).toBeNull();
  });
});
