import { describe, expect, it } from 'vitest';
import {
  buildPendingWorkflowGuide,
  buildPendingWorkflowGuideFromMessages,
  resolvePendingWorkflowGuide,
  resolvePendingWorkflowGuideWithKey,
} from './pendingWorkflowUtils';

describe('buildPendingWorkflowGuide', () => {
  it('builds a clarification guide with short-answer options', () => {
    const guide = buildPendingWorkflowGuide({
      _agent_plan: {
        mode: 'generate_dita_preview',
        status: 'clarification_required',
        preview: {
          clarification_needed: true,
          clarification_question: 'Do you want 20 concept, task, reference, or generic topic files?',
          clarification_request: {
            options: ['concept', 'task', 'reference', 'topic'],
          },
        },
      },
    });

    expect(guide).not.toBeNull();
    expect(guide?.kind).toBe('clarification');
    expect(guide?.title).toBe('One quick detail');
    expect(guide?.placeholder).toContain('concept');
    expect(guide?.suggestedReplies).toEqual(['concept', 'task', 'reference', 'topic']);
  });

  it('builds a review guide from approval state', () => {
    const guide = buildPendingWorkflowGuide({
      _approval_state: {
        state: 'required',
        kind: 'review',
        prompt: 'Review the proposed generate_dita bundle before generation.',
        allowed_responses: ['approve', 'continue'],
      },
    });

    expect(guide).not.toBeNull();
    expect(guide?.kind).toBe('review');
    expect(guide?.title).toBe('Ready when you are');
    expect(guide?.placeholder).toContain('approve');
    expect(guide?.suggestedReplies).toEqual(['approve', 'continue']);
  });

  it('does not show review guide when generate_dita already produced a bundle (stale approval)', () => {
    const guide = buildPendingWorkflowGuide({
      _approval_state: {
        state: 'required',
        pending_tool_name: 'generate_dita',
        allowed_responses: ['approve', 'continue'],
      },
      generate_dita: {
        download_url: '/api/v1/chat/artifacts/bundle.zip',
        summary: 'Done',
      },
    });
    expect(guide).toBeNull();
  });

  it('does not show review guide when execution already completed (stale approval)', () => {
    const guide = buildPendingWorkflowGuide({
      _approval_state: {
        state: 'required',
        pending_tool_name: 'generate_dita',
        allowed_responses: ['approve'],
      },
      _agent_execution: { status: 'completed', steps: [{ id: '1', title: 'Generate', status: 'completed' }] },
    });
    expect(guide).toBeNull();
  });

  it('does not suppress approval for a different pending tool when a bundle exists', () => {
    const guide = buildPendingWorkflowGuide({
      _approval_state: {
        state: 'required',
        pending_tool_name: 'create_job',
        allowed_responses: ['yes', 'no'],
      },
      generate_dita: {
        download_url: '/api/v1/chat/artifacts/bundle.zip',
      },
    });
    expect(guide).not.toBeNull();
    expect(guide?.kind).toBe('review');
  });

  it('ignores stale approval on an older assistant row when a newer row has the bundle', () => {
    const messages = [
      { role: 'user', tool_results: undefined },
      {
        role: 'assistant',
        tool_results: {
          _approval_state: {
            state: 'required',
            pending_tool_name: 'generate_dita',
            allowed_responses: ['approve', 'continue'],
          },
        },
      },
      {
        role: 'assistant',
        tool_results: {
          generate_dita: {
            download_url: '/api/v1/ai/bundle/jira/run/download',
            bundle_summary: 'Generated a DITA bundle with 5 topic files.',
            artifact_counts: { total_files: 5, topic_files: 5, map_files: 0 },
          },
        },
      },
    ];
    expect(buildPendingWorkflowGuideFromMessages(messages)).toBeNull();
    expect(resolvePendingWorkflowGuide(messages, null)).toBeNull();
  });

  it('suppresses review guide when delivery complete is proven only by artifact_counts', () => {
    const guide = buildPendingWorkflowGuide({
      _approval_state: { state: 'required', pending_tool_name: 'generate_dita', allowed_responses: ['approve'] },
      generate_dita: {
        artifact_counts: { total_files: 3, topic_files: 3, map_files: 0 },
      },
    });
    expect(guide).toBeNull();
  });

  it('does not resurrect history approval when the live stream blob already has a finished bundle', () => {
    const messages = [
      {
        role: 'assistant',
        tool_results: {
          _approval_state: {
            state: 'required',
            pending_tool_name: 'generate_dita',
            allowed_responses: ['approve'],
          },
        },
      },
    ];
    const streaming = {
      generate_dita: {
        download_url: '/api/v1/ai/bundle/x/y/download',
        bundle_summary: 'Done',
      },
      _approval_state: {
        state: 'required',
        pending_tool_name: 'generate_dita',
        allowed_responses: ['approve'],
      },
    };
    expect(resolvePendingWorkflowGuide(messages, streaming)).toBeNull();
  });

  it('resolvePendingWorkflowGuideWithKey matches resolvePendingWorkflowGuide and returns a source key', () => {
    const streaming = {
      _approval_state: {
        state: 'required',
        pending_tool_name: 'generate_dita',
        allowed_responses: ['approve', 'continue'],
      },
    };
    const resolved = resolvePendingWorkflowGuideWithKey([], streaming);
    expect(resolved.guide).toEqual(resolvePendingWorkflowGuide([], streaming));
    expect(resolved.guide).not.toBeNull();
    expect(resolved.sourceKey).toMatch(/^stream\x1f/);
  });

  it('uses message id in source key for persisted thread guides', () => {
    const messages = [
      {
        role: 'assistant',
        id: 'm-1',
        tool_results: {
          _approval_state: {
            state: 'required',
            allowed_responses: ['yes'],
          },
        },
      },
    ];
    const resolved = resolvePendingWorkflowGuideWithKey(messages, null);
    expect(resolved.guide?.kind).toBe('review');
    expect(resolved.sourceKey).toContain('msg:m-1');
  });
});
