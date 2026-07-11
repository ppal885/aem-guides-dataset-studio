import { describe, expect, it, vi } from 'vitest';
import { regenerateAssistant } from './chat';

function sseDoneResponse() {
  const encoder = new TextEncoder();
  const chunk = encoder.encode('data: {"type":"done"}\n\n');
  return {
    ok: true,
    body: {
      getReader: () => {
        let sent = false;
        return {
          read: async () => {
            if (!sent) {
              sent = true;
              return { done: false, value: chunk };
            }
            return { done: true, value: undefined };
          },
          releaseLock: () => {},
        };
      },
    },
  };
}

describe('regenerateAssistant', () => {
  it('POSTs human_prompts and context without generation_options', async () => {
    const fetchMock = vi.fn().mockResolvedValue(sseDoneResponse());
    vi.stubGlobal('fetch', fetchMock);

    const noop = () => {};
    await regenerateAssistant('session-abc', { onDone: noop }, {
      humanPrompts: true,
      context: { source_page: '/chat' },
    });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    const body = JSON.parse(init.body as string);
    expect(body.human_prompts).toBe(true);
    expect(body.context).toEqual({ source_page: '/chat' });
    expect(body.generation_options).toBeUndefined();

    vi.unstubAllGlobals();
  });
});
