import { describe, it, expect, vi } from 'vitest';
import { parseNDJSONLine, extractCustomEventPayload, processNDJSONStream } from '@/lib/chat/stream-transformer';

describe('parseNDJSONLine', () => {
    it('parses valid JSON line', () => {
        const result = parseNDJSONLine('{"event": "on_chain_start", "name": "test"}');
        expect(result).toEqual({ event: 'on_chain_start', name: 'test' });
    });

    it('returns null for empty line', () => {
        expect(parseNDJSONLine('')).toBeNull();
        expect(parseNDJSONLine('   ')).toBeNull();
    });

    it('returns null for invalid JSON', () => {
        expect(parseNDJSONLine('not json')).toBeNull();
        expect(parseNDJSONLine('{incomplete')).toBeNull();
    });
});

describe('extractCustomEventPayload', () => {
    it('extracts payload from on_custom_event', () => {
        const event = {
            event: 'on_custom_event',
            name: 'plan-update',
            data: { step_id: '123', status: 'in_progress' },
            metadata: { step_id: '123', agent_name: 'planner' }
        };

        const result = extractCustomEventPayload(event);
        expect(result).toEqual({
            type: 'plan-update',
            data: { step_id: '123', status: 'in_progress' },
            stepId: '123',
            agentName: 'planner'
        });
    });

    it('returns null for non-custom events', () => {
        expect(extractCustomEventPayload({ event: 'on_chain_start' })).toBeNull();
        expect(extractCustomEventPayload(null)).toBeNull();
        expect(extractCustomEventPayload({})).toBeNull();
    });

    it('handles missing optional fields', () => {
        const event = {
            event: 'on_custom_event',
            name: 'test'
        };

        const result = extractCustomEventPayload(event);
        expect(result).toEqual({
            type: 'test',
            data: {},
            stepId: undefined,
            agentName: undefined
        });
    });
});

describe('processNDJSONStream', () => {
    it('parses NDJSON and yields events', async () => {
        const input = '{"event": "on_chain_start", "name": "test"}\n{"event": "on_chat_model_stream", "data": {"chunk": "hello"}}\n';
        const encoder = new TextEncoder();
        const readable = new ReadableStream({
            start(controller) {
                controller.enqueue(encoder.encode(input));
                controller.close();
            }
        });

        const generator = processNDJSONStream(readable);
        const events = [];
        for await (const event of generator) {
            events.push(event);
        }

        expect(events).toHaveLength(2);
        expect(events[0]).toEqual({ event: 'on_chain_start', name: 'test' });
        expect(events[1]).toEqual({ event: 'on_chat_model_stream', data: { chunk: 'hello' } });
    });

    it('calls onCustomEvent for custom events', async () => {
        const onCustomEvent = vi.fn();
        const input = JSON.stringify({
            event: 'on_custom_event',
            name: 'ui_step_update',
            data: { step_id: '123', status: 'in_progress' },
            metadata: { step_id: '123' }
        }) + '\n';

        const encoder = new TextEncoder();
        const readable = new ReadableStream({
            start(controller) {
                controller.enqueue(encoder.encode(input));
                controller.close();
            }
        });

        const generator = processNDJSONStream(readable, onCustomEvent);
        // Consume generator
        for await (const _ of generator) { }

        expect(onCustomEvent).toHaveBeenCalledTimes(1);
        expect(onCustomEvent).toHaveBeenCalledWith({
            type: 'ui_step_update',
            data: { step_id: '123', status: 'in_progress' },
            stepId: '123',
            agentName: undefined
        });
    });

    it('handles split chunks (buffering)', async () => {
        const input1 = '{"event": "on_chain_star';
        const input2 = 't", "name": "test"}\n';

        const encoder = new TextEncoder();
        const readable = new ReadableStream({
            start(controller) {
                controller.enqueue(encoder.encode(input1));
                controller.enqueue(encoder.encode(input2));
                controller.close();
            }
        });

        const generator = processNDJSONStream(readable);
        const events = [];
        for await (const event of generator) {
            events.push(event);
        }

        expect(events).toHaveLength(1);
        expect(events[0]).toEqual({ event: 'on_chain_start', name: 'test' });
    });
});
