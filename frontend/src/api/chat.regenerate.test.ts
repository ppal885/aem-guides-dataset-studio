import { describe, expect, it, vi } from 'vitest';
import { regenerateAssistant, type ChatDitaGenerationOptions } from './chat';

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
  it('POSTs generation_options when generationOptions is set', async () => {
    const fetchMock = vi.fn().mockResolvedValue(sseDoneResponse());
    vi.stubGlobal('fetch', fetchMock);

    const noop = () => {};
    await regenerateAssistant('session-abc', { onDone: noop }, {
      generationOptions: {
        dita_type: 'reference',
        style_strictness: 'low',
        strict_validation: false,
        preserve_prolog: true,
        xref_placeholders: true,
        auto_ids: false,
        output_mode: 'xml_only',
        authoring_pattern: 'cisco_task',
        preserve_reference_doctype: true,
      } as ChatDitaGenerationOptions,
    });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    const body = JSON.parse(init.body as string);
    expect(body.generation_options).toBeDefined();
    expect(body.generation_options.dita_type).toBe('reference');
    expect(body.generation_options.style_strictness).toBe('low');
    expect(body.generation_options.strict_validation).toBe(false);
    expect(body.generation_options.output_mode).toBe('xml_only');
    expect(body.generation_options.authoring_pattern).toBe('cisco_task');

    vi.unstubAllGlobals();
  });
});
