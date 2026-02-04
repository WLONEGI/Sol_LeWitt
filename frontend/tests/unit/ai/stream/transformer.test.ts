import { describe, expect, it, vi } from 'vitest';
import { extractCustomEventPayload, parseNDJSONLine } from '@/ai/stream/transformer';

describe('parseNDJSONLine', () => {
  it('parses valid JSON line', () => {
    const result = parseNDJSONLine('{"event":"ok"}');
    expect(result).toEqual({ event: 'ok' });
  });

  it('returns null for empty or invalid line', () => {
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => { });

    expect(parseNDJSONLine('')).toBeNull();
    expect(parseNDJSONLine('not-json')).toBeNull();

    warnSpy.mockRestore();
  });
});

describe('extractCustomEventPayload', () => {
  it('returns null for non custom events', () => {
    expect(extractCustomEventPayload({ event: 'other' })).toBeNull();
  });

  it('extracts payload with defaults', () => {
    const payload = extractCustomEventPayload({
      event: 'on_custom_event',
      name: 'plan_update',
      data: { ok: true },
      metadata: { step_id: 's1', agent_name: 'planner' },
    });

    expect(payload).toEqual({
      type: 'plan_update',
      data: { ok: true },
      stepId: 's1',
      agentName: 'planner',
    });
  });
});
