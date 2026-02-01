import { NextRequest } from 'next/server';
import { v4 as uuidv4 } from 'uuid';
import { createUIMessageStreamResponse } from 'ai';

// Node.js runtime for longer timeouts (Pro plan: up to 5 mins)
export const runtime = 'nodejs';
export const maxDuration = 300;

export async function POST(req: NextRequest) {
    try {
        const { messages, thread_id, pptx_template_base64 } = await req.json();

        const lastMessage = messages[messages.length - 1];
        const userContent = typeof lastMessage.content === 'string'
            ? lastMessage.content
            : lastMessage.parts?.filter((p: any) => p.type === 'text').map((p: any) => p.text).join('') || '';

        console.log(`[Stream] Received request. Thread ID: ${thread_id || 'New'}`);

        const backendBody = {
            input: {
                messages: [{ role: "user", content: userContent }],
                ...(pptx_template_base64 ? { pptx_template_base64 } : {})
            },
            config: {
                configurable: { thread_id: thread_id },
                recursion_limit: 50
            }
        };

        const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000';
        const response = await fetch(`${BACKEND_URL}/api/chat/stream_events`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                ...(thread_id ? { 'X-Thread-Id': thread_id } : {})
            },
            body: JSON.stringify(backendBody),
        });

        if (!response.ok) {
            console.error(`[Stream] Backend error: ${response.status}`);
            return new Response(JSON.stringify({ error: 'Backend error' }), { status: response.status });
        }

        if (!response.body) {
            return new Response(JSON.stringify({ error: 'No response body' }), { status: 500 });
        }

        return createUIMessageStreamResponse({
            stream: new ReadableStream({
                async start(controller) {
                    const reader = response.body!.getReader();
                    const decoder = new TextDecoder();
                    let buffer = '';

                    // State for tracking multi-agent streams
                    let currentReasoningId: string | null = null;
                    let currentTextId: string | null = null;
                    let isReasoning = false;
                    // Track tool calls to associate results
                    const toolCallMap = new Map<string, string>(); // run_id -> toolCallId

                    try {
                        while (true) {
                            const { done, value } = await reader.read();
                            if (done) break;

                            buffer += decoder.decode(value, { stream: true });
                            const lines = buffer.split('\n');
                            buffer = lines.pop() || '';

                            for (const line of lines) {
                                if (!line.trim() || line.startsWith(':')) continue;
                                if (!line.startsWith('data: ')) continue;

                                try {
                                    const eventData = JSON.parse(line.slice(6));
                                    const event = eventData.event;

                                    switch (event) {
                                        case 'on_chain_start':
                                            if (eventData.name && ['planner', 'researcher', 'writer', 'reviewer', 'improver', 'presenter'].includes(eventData.name)) {
                                                controller.enqueue({
                                                    type: 'data-ui_step_update',
                                                    data: {
                                                        status: 'active',
                                                        label: eventData.name,
                                                        id: uuidv4()
                                                    }
                                                } as any);
                                            }
                                            break;

                                        case 'on_chain_end':
                                            if (eventData.name && ['planner', 'researcher', 'writer', 'reviewer', 'improver', 'presenter'].includes(eventData.name)) {
                                                controller.enqueue({
                                                    type: 'data-ui_step_update',
                                                    data: {
                                                        status: 'completed',
                                                        label: eventData.name,
                                                        output: eventData.data?.output || null,
                                                        id: uuidv4()
                                                    }
                                                } as any);
                                            }
                                            break;

                                        case 'on_tool_start': {
                                            // Handle Tool Calls
                                            // LangChain eventData.data.input should be the args
                                            const toolName = eventData.name;
                                            // Filter out internal LangChain tools or irrelevant ones if needed
                                            if (toolName && !toolName.startsWith('__')) {
                                                const runId = eventData.run_id;
                                                const toolCallId = uuidv4();
                                                if (runId) toolCallMap.set(runId, toolCallId);

                                                controller.enqueue({
                                                    type: 'tool-call',
                                                    toolCallId: toolCallId,
                                                    toolName: toolName,
                                                    args: eventData.data?.input || {}
                                                } as any);
                                            }
                                            break;
                                        }

                                        case 'on_tool_end': {
                                            const runId = eventData.run_id;
                                            const toolCallId = runId ? toolCallMap.get(runId) : null;

                                            if (toolCallId) {
                                                controller.enqueue({
                                                    type: 'tool-result',
                                                    toolCallId: toolCallId,
                                                    result: eventData.data?.output
                                                } as any);
                                                // Optional: clean up map if needed, but keeping might be safer
                                            }
                                            break;
                                        }

                                        case 'on_chat_model_stream': {
                                            const chunk = eventData?.data?.chunk;
                                            let content: any = '';

                                            if (chunk && typeof chunk === 'object' && 'content' in chunk) {
                                                content = chunk.content;
                                            } else if (typeof chunk === 'string') {
                                                content = chunk;
                                            }

                                            if (Array.isArray(content)) {
                                                for (const part of content) {
                                                    if (part.type === 'thought' && part.thought) {
                                                        // Detect start of NEW reasoning block
                                                        if (!isReasoning) {
                                                            isReasoning = true;
                                                            currentReasoningId = uuidv4();
                                                            currentTextId = null; // Reset text ID
                                                        }

                                                        controller.enqueue({
                                                            type: 'reasoning-delta',
                                                            id: currentReasoningId,
                                                            delta: part.thought
                                                        } as any);
                                                    } else if (part.type === 'text' && part.text) {
                                                        // Detect start of NEW text block (transition from reasoning or start)
                                                        if (isReasoning || !currentTextId) {
                                                            isReasoning = false;
                                                            currentTextId = uuidv4();
                                                            currentReasoningId = null; // Reset reasoning ID
                                                        }

                                                        controller.enqueue({
                                                            type: 'text-delta',
                                                            id: currentTextId,
                                                            delta: part.text
                                                        } as any);
                                                    }
                                                }
                                            } else if (typeof content === 'string' && content) {
                                                // Fallback for simple string content (treat as text)
                                                if (isReasoning || !currentTextId) {
                                                    isReasoning = false;
                                                    currentTextId = uuidv4();
                                                    currentReasoningId = null;
                                                }

                                                controller.enqueue({
                                                    type: 'text-delta',
                                                    id: currentTextId,
                                                    delta: content
                                                } as any);
                                            }
                                            break;
                                        }
                                    }
                                } catch (e) {
                                    console.error('Error parsing backend SSE line:', e);
                                }
                            }
                        }
                    } catch (error) {
                        controller.error(error);
                    } finally {
                        controller.close();
                    }
                }
            })
        });

    } catch (error: any) {
        console.error('[Stream] Handler error:', error);
        return new Response(JSON.stringify({ error: error.message }), { status: 500 });
    }
}
