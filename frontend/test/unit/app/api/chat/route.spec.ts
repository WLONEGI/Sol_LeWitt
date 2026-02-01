import { describe, it, expect, vi, beforeEach } from 'vitest';
import { POST } from '@/app/api/chat/route';
import { NextRequest } from 'next/server';

// Mock dependencies
vi.mock('uuid', () => ({
    v4: () => 'test-uuid-1234'
}));

// Mock NextRequest behavior since we are in JSDOM/Node environment
class MockNextRequest {
    private body: any;

    constructor(body: any) {
        this.body = body;
    }

    async json() {
        return this.body;
    }
}

describe('BFF POST Handler Integration', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        // Reset fetch mock
        global.fetch = vi.fn();
    });

    it('should transform backend text stream events to Vercel AI SDK text parts', async () => {
        // 1. Setup Request
        const req = new MockNextRequest({
            messages: [{ role: 'user', content: 'hello' }],
            thread_id: 'test-thread'
        }) as unknown as NextRequest;

        // 2. Mock Backend Response (SSE Stream)
        const mockStream = new ReadableStream({
            start(controller) {
                // Backend sends "on_chat_model_stream" with text chunk
                const event = {
                    event: 'on_chat_model_stream',
                    data: {
                        chunk: { content: 'Hello world' }
                    }
                };
                controller.enqueue(new TextEncoder().encode(`data: ${JSON.stringify(event)}\n\n`));
                controller.close();
            }
        });

        (global.fetch as any).mockResolvedValue({
            ok: true,
            status: 200,
            body: mockStream
        });

        // 3. Execute POST
        const res = await POST(req);
        expect(res.status).toBe(200);

        // 4. Verify Response Stream Content
        // The Vercel AI SDK V2 Protocol output is somewhat opaque string format.
        // But createUIMessageStreamResponse produces a stream of parts.
        // We can read it to verify content presence.
        const reader = res.body?.getReader();
        const decoder = new TextDecoder();
        let output = '';

        while (true) {
            const { done, value } = await reader!.read();
            if (done) break;
            output += decoder.decode(value);
        }

        // Check if output contains the text delta
        // Vercel Protocol: 0:"Hello world" (approximate format)
        expect(output).toContain('Hello world');
    });

    it('should transform backend tool events to tool calls', async () => {
        const req = new MockNextRequest({
            messages: [{ role: 'user', content: 'search' }],
            thread_id: 'test-thread'
        }) as unknown as NextRequest;

        const mockStream = new ReadableStream({
            start(controller) {
                // Backend sends "on_tool_start"
                const event = {
                    event: 'on_tool_start',
                    name: 'google_search',
                    run_id: 'run-123',
                    data: {
                        input: { query: 'vitest' }
                    }
                };
                controller.enqueue(new TextEncoder().encode(`data: ${JSON.stringify(event)}\n\n`));
                controller.close();
            }
        });

        (global.fetch as any).mockResolvedValue({
            ok: true,
            status: 200,
            body: mockStream
        });

        const res = await POST(req);
        const reader = res.body?.getReader();
        const decoder = new TextDecoder();
        let output = '';

        while (true) {
            const { done, value } = await reader!.read();
            if (done) break;
            output += decoder.decode(value);
        }

        // Verify tool usage is present in the stream
        // Vercel SDK format for tools is complex, but we expect "google_search" and "vitest" to be in the output
        expect(output).toContain('google_search');
        expect(output).toContain('vitest');
    });

    it('should transform backend reasoning events to reasoning parts', async () => {
        const req = new MockNextRequest({
            messages: [{ role: 'user', content: 'reason' }],
            thread_id: 'test-thread'
        }) as unknown as NextRequest;

        const mockStream = new ReadableStream({
            start(controller) {
                // Backend sends "on_chat_model_stream" with reasoning
                const event = {
                    event: 'on_chat_model_stream',
                    data: {
                        chunk: {
                            content: [
                                { type: 'thought', thought: 'Thinking process...' },
                                { type: 'text', text: 'Result' }
                            ]
                        }
                    }
                };
                controller.enqueue(new TextEncoder().encode(`data: ${JSON.stringify(event)}\n\n`));
                controller.close();
            }
        });

        (global.fetch as any).mockResolvedValue({
            ok: true,
            status: 200,
            body: mockStream
        });

        const res = await POST(req);
        const reader = res.body?.getReader();
        const decoder = new TextDecoder();
        let output = '';

        while (true) {
            const { done, value } = await reader!.read();
            if (done) break;
            output += decoder.decode(value);
        }

        // Verify reasoning is present
        expect(output).toContain('Thinking process...');
        expect(output).toContain('Result');
    });
});
