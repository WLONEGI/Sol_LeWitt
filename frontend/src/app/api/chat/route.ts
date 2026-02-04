import { NextRequest } from 'next/server';
import { v4 as uuidv4 } from 'uuid';
import { createUIMessageStreamResponse } from 'ai';
import * as fs from 'fs';
import * as path from 'path';

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
                    const logDir = path.resolve(process.cwd(), '..', 'logs');
                    let logPath: string | null = null;

                    // State for tracking multi-agent streams
                    let currentReasoningId: string | null = null;
                    let currentTextId: string | null = null;
                    let currentRunId: string | null = null;

                    // Track tool calls to associate results
                    const toolCallMap = new Map<string, string>(); // run_id -> toolCallId

                    try {
                        try {
                            fs.mkdirSync(logDir, { recursive: true });
                            logPath = path.join(logDir, 'frontend_event.log');
                        } catch (logErr) {
                            console.error('Failed to ensure logs directory:', logErr);
                        }

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
                                    // Log the full stream event for debugging
                                    const logEntry = `[${new Date().toISOString()}] [LangServe Event] ${eventData.event}: ${JSON.stringify(eventData)}\n`;
                                    console.log(`[LangServe Event] ${eventData.event}:`, JSON.stringify(eventData));

                                    if (logPath) {
                                        try {
                                            fs.appendFileSync(logPath, logEntry);
                                        } catch (logErr) {
                                            console.error('Failed to write to frontend_event.log:', logErr);
                                        }
                                    }

                                    const event = eventData.event;

                                    switch (event) {
                                        // Debug UI (on_chain_start/end) removed as per request

                                        case 'on_custom_event': {
                                            const eventName = eventData.name;
                                            if (eventName === 'plan_updated') {
                                                console.log("[Stream] Custom event 'plan_updated' received.");
                                                // Send the plan data
                                                controller.enqueue({
                                                    type: 'data-plan',
                                                    data: eventData.data
                                                } as any);
                                            } else if (eventName === 'slide_outline_updated') {
                                                console.log("[Stream] Custom event 'slide_outline_updated' received.");
                                                // 1. Send the outline data part
                                                controller.enqueue({
                                                    type: 'data-outline',
                                                    data: eventData.data
                                                } as any);
                                            } else if (eventName === 'title_generated') {
                                                console.log(`[Stream] Custom event 'title_generated' received: ${eventData.data?.title}`);
                                                // Forward title update to client
                                                controller.enqueue({
                                                    type: 'data-title-update',
                                                    title: eventData.data?.title
                                                } as any);
                                            }
                                            // [Forward Research Events]
                                            else if (eventName === 'research_worker_start') {
                                                controller.enqueue({
                                                    type: 'data-research-start',
                                                    data: eventData.data
                                                } as any);
                                            } else if (eventName === 'research_worker_token') {
                                                controller.enqueue({
                                                    type: 'data-research-token',
                                                    data: eventData.data
                                                } as any);
                                            } else if (eventName === 'research_worker_complete') {
                                                controller.enqueue({
                                                    type: 'data-research-complete',
                                                    data: eventData.data
                                                } as any);
                                            }
                                            break;
                                        }

                                        case 'on_chat_model_stream': {
                                            const meta = eventData.metadata || {};
                                            const node = meta.langgraph_node;
                                            const checkpoint = meta.langgraph_checkpoint_ns || meta.checkpoint_ns || '';
                                            const isResearcherSubgraph = typeof checkpoint === 'string' && checkpoint.includes('researcher:');
                                            const isPlanner = node === 'planner' || (typeof checkpoint === 'string' && checkpoint.includes('planner:'));
                                            if (isPlanner || (isResearcherSubgraph && (node === 'manager' || node === 'research_worker'))) {
                                                break;
                                            }
                                            const runId = eventData.run_id;
                                            const runName = eventData.name;
                                            currentRunId = runId;

                                            const chunk = eventData?.data?.chunk;
                                            const isLastChunk = chunk?.chunk_position === 'last';
                                            let content: any = '';

                                            if (chunk && typeof chunk === 'object' && 'content' in chunk) {
                                                content = chunk.content;
                                            } else if (typeof chunk === 'string') {
                                                console.log(`[Stream] Received string chunk: ${chunk.substring(0, 50)}...`);
                                                content = chunk;
                                            }

                                            if (Array.isArray(content)) {
                                                for (const part of content) {
                                                    if (part.type === 'thinking' && part.thinking) {
                                                        // Handling THINKING part
                                                        const reasoningContent = part.thinking;

                                                        // If we were outputting text, must end it first
                                                        if (currentTextId) {
                                                            console.log(`[Stream] Ending text ${currentTextId} to start reasoning`);
                                                            controller.enqueue({
                                                                type: 'text-end',
                                                                id: currentTextId
                                                            } as any);
                                                            currentTextId = null;
                                                        }

                                                        // If we are not already in a reasoning block, start one
                                                        if (!currentReasoningId) {
                                                            currentReasoningId = uuidv4();
                                                            console.log(`[Stream] Starting reasoning block: ${currentReasoningId}`);
                                                            controller.enqueue({
                                                                type: 'reasoning-start',
                                                                id: currentReasoningId
                                                            } as any);
                                                        }

                                                        controller.enqueue({
                                                            type: 'reasoning-delta',
                                                            id: currentReasoningId,
                                                            delta: reasoningContent
                                                        } as any);

                                                    } else if (part.type === 'text' && part.text) {
                                                        // Handling TEXT part

                                                        // If we were outputting reasoning, must end it first
                                                        if (currentReasoningId) {
                                                            console.log(`[Stream] Ending reasoning ${currentReasoningId} to start text`);
                                                            controller.enqueue({
                                                                type: 'reasoning-end',
                                                                id: currentReasoningId
                                                            } as any);
                                                            currentReasoningId = null;
                                                        }

                                                        // If we are not already in a text block, start one
                                                        if (!currentTextId) {
                                                            currentTextId = uuidv4();
                                                            console.log(`[Stream] Starting text block: ${currentTextId}`);
                                                            controller.enqueue({
                                                                type: 'text-start',
                                                                id: currentTextId
                                                            } as any);
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

                                                if (currentReasoningId) {
                                                    controller.enqueue({
                                                        type: 'reasoning-end',
                                                        id: currentReasoningId
                                                    } as any);
                                                    currentReasoningId = null;
                                                }

                                                if (!currentTextId) {
                                                    currentTextId = uuidv4();
                                                    controller.enqueue({
                                                        type: 'text-start',
                                                        id: currentTextId
                                                    } as any);
                                                }

                                                controller.enqueue({
                                                    type: 'text-delta',
                                                    id: currentTextId,
                                                    delta: content
                                                } as any);
                                            }

                                            // Explicitly close blocks when chunk_position: "last" is received
                                            if (isLastChunk) {
                                                console.log(`[Stream] Received last chunk for runId: ${runId}`);
                                                if (currentTextId) {
                                                    controller.enqueue({ type: 'text-end', id: currentTextId } as any);
                                                    currentTextId = null;
                                                }
                                                if (currentReasoningId) {
                                                    controller.enqueue({ type: 'reasoning-end', id: currentReasoningId } as any);
                                                    currentReasoningId = null;
                                                }
                                            }
                                            break;
                                        }
                                    }
                                } catch (e) {
                                    console.error('Error parsing backend SSE line:', e, 'Raw line:', line);
                                }
                            }
                        }

                        console.log(`[Stream] Backend closed the reader. Done.`);
                    } catch (error) {
                        console.error('[Stream] Reader loop error:', error);
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
