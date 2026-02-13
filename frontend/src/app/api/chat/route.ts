import { NextRequest } from 'next/server';
import { v4 as uuidv4 } from 'uuid';
import { createUIMessageStreamResponse } from 'ai';
import * as fs from 'fs';
import * as path from 'path';
import { normalizePlanUpdateData } from '@/features/chat/types/plan';

// Node.js runtime for longer timeouts (Pro plan: up to 5 mins)
export const runtime = 'nodejs';
export const maxDuration = 300;
const ALLOWED_PRODUCT_TYPES = new Set(['slide', 'design', 'comic']);

export async function POST(req: NextRequest) {
    try {
        const {
            messages,
            thread_id,
            pptx_template_base64,
            selected_image_inputs,
            attachments,
            interrupt_intent,
            product_type,
            aspect_ratio,
        } = await req.json();
        const authHeader = req.headers.get("authorization") || req.headers.get("Authorization");
        if (!authHeader || !authHeader.toLowerCase().startsWith("bearer ")) {
            return new Response(JSON.stringify({ error: "Unauthorized" }), { status: 401 });
        }

        const lastMessage = messages[messages.length - 1];

        const userContent = typeof lastMessage.content === 'string'
            ? lastMessage.content
            : lastMessage.parts?.filter((p: any) => p.type === 'text').map((p: any) => p.text).join('') || '';

        console.log(`[Stream] Received request. Thread ID: ${thread_id || 'New'}, product_type: ${product_type}`);
        // console.log("Incoming body keys:", Object.keys(await req.clone().json())); // req.json() consumed above


        const normalizedProductType =
            typeof product_type === 'string' && ALLOWED_PRODUCT_TYPES.has(product_type)
                ? product_type
                : undefined;

        const backendBody = {
            input: {
                messages: [{ role: "user", content: userContent }],
                selected_image_inputs: Array.isArray(selected_image_inputs) ? selected_image_inputs : [],
                attachments: Array.isArray(attachments) ? attachments : [],
                interrupt_intent: Boolean(interrupt_intent),
                ...(normalizedProductType ? { product_type: normalizedProductType } : {}),
                ...(typeof aspect_ratio === 'string' && aspect_ratio ? { aspect_ratio } : {}),
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
                'Authorization': authHeader,
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
                    let plannerTextBuffer = '';
                    let writerTextBuffer = '';
                    let coordinatorTextBuffer = '';
                    let coordinatorRenderedResponse = '';
                    let coordinatorResponseCompleted = false;

                    // Track tool calls to associate results
                    const toolCallMap = new Map<string, string>(); // run_id -> toolCallId

                    const extractFirstJson = (input: string) => {
                        const match = input.match(/\{[\s\S]*\}/);
                        return match ? match[0] : null;
                    };

                    const normalizeCoordinatorFollowups = (raw: any) => {
                        if (!Array.isArray(raw)) return [] as Array<{ id: string; prompt: string }>;
                        const normalized: Array<{ id: string; prompt: string }> = [];
                        const seenPrompt = new Set<string>();

                        for (const entry of raw) {
                            if (!entry || typeof entry !== 'object') continue;
                            const prompt = typeof entry.prompt === 'string' ? entry.prompt.trim() : '';
                            if (!prompt) continue;
                            const dedupeKey = prompt.toLowerCase();
                            if (seenPrompt.has(dedupeKey)) continue;
                            seenPrompt.add(dedupeKey);
                            const safeId =
                                typeof entry.id === 'string' && entry.id.trim()
                                    ? entry.id.trim()
                                    : `followup_${normalized.length + 1}`;
                            normalized.push({
                                id: safeId,
                                prompt,
                            });
                            if (normalized.length >= 3) break;
                        }

                        return normalized;
                    };

                    const extractCoordinatorResponseFromJsonBuffer = (jsonBuffer: string) => {
                        const keyMatch = /"response"\s*:\s*"/.exec(jsonBuffer);
                        if (!keyMatch || typeof keyMatch.index !== 'number') {
                            return { decoded: '', completed: false };
                        }

                        const start = keyMatch.index + keyMatch[0].length;
                        let decoded = '';
                        let escapeMode = false;
                        let unicodeMode = 0;
                        let unicodeDigits = '';

                        for (let i = start; i < jsonBuffer.length; i++) {
                            const ch = jsonBuffer[i];

                            if (unicodeMode > 0) {
                                if (!/[0-9a-fA-F]/.test(ch)) {
                                    unicodeMode = 0;
                                    unicodeDigits = '';
                                    continue;
                                }
                                unicodeDigits += ch;
                                unicodeMode -= 1;
                                if (unicodeMode === 0 && unicodeDigits.length === 4) {
                                    decoded += String.fromCharCode(parseInt(unicodeDigits, 16));
                                    unicodeDigits = '';
                                }
                                continue;
                            }

                            if (escapeMode) {
                                if (ch === 'n') decoded += '\n';
                                else if (ch === 'r') decoded += '\r';
                                else if (ch === 't') decoded += '\t';
                                else if (ch === 'b') decoded += '\b';
                                else if (ch === 'f') decoded += '\f';
                                else if (ch === '"' || ch === '\\' || ch === '/') decoded += ch;
                                else if (ch === 'u') {
                                    unicodeMode = 4;
                                    unicodeDigits = '';
                                }
                                escapeMode = false;
                                continue;
                            }

                            if (ch === '\\') {
                                escapeMode = true;
                                continue;
                            }

                            if (ch === '"') {
                                return { decoded, completed: true };
                            }

                            decoded += ch;
                        }

                        return { decoded, completed: false };
                    };

                    const emitCoordinatorResponseDeltaFromBuffer = () => {
                        if (coordinatorResponseCompleted) return;
                        const { decoded, completed } = extractCoordinatorResponseFromJsonBuffer(coordinatorTextBuffer);
                        if (!decoded) {
                            if (completed) {
                                coordinatorResponseCompleted = true;
                            }
                            return;
                        }

                        if (!currentTextId) {
                            currentTextId = uuidv4();
                            controller.enqueue({
                                type: 'text-start',
                                id: currentTextId
                            } as any);
                        }

                        if (decoded.startsWith(coordinatorRenderedResponse)) {
                            const delta = decoded.slice(coordinatorRenderedResponse.length);
                            if (delta) {
                                controller.enqueue({
                                    type: 'text-delta',
                                    id: currentTextId,
                                    delta
                                } as any);
                                coordinatorRenderedResponse = decoded;
                            }
                        }

                        if (completed) {
                            coordinatorResponseCompleted = true;
                        }
                    };

                    const logToFile = (message: string) => {
                        if (!logPath) return;
                        try {
                            fs.appendFileSync(logPath, message);
                        } catch (logErr) {
                            console.error('Failed to write to frontend_event.log:', logErr);
                        }
                    };

                    const emitPlanFromParsed = (parsed: any) => {
                        const steps = parsed?.steps ?? parsed?.plan ?? [];
                        const normalized = normalizePlanUpdateData({
                            plan: Array.isArray(steps) ? steps : [],
                            ui_type: 'plan_update',
                            title: 'Execution Plan',
                            description: 'The updated execution plan.'
                        });
                        controller.enqueue({
                            type: 'data-plan_update',
                            data: normalized
                        } as any);
                    };

                    const emitOutlineFromParsed = (parsed: any) => {
                        const slides = Array.isArray(parsed?.slides) ? parsed.slides : [];
                        if (slides.length === 0) return;
                        controller.enqueue({
                            type: 'data-outline',
                            data: {
                                slides,
                                ui_type: 'slide_outline',
                                title: 'Slide Outline',
                                description: 'The generated slide outline and narrative map.'
                            }
                        } as any);
                    };

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

                                        case 'error': {
                                            const payload = eventData?.data;
                                            const kind = typeof payload?.kind === 'string' ? payload.kind : '';
                                            const message =
                                                typeof payload?.message === 'string' && payload.message.trim().length > 0
                                                    ? payload.message
                                                    : (typeof payload === 'string' ? payload : '処理中にエラーが発生しました。');

                                            if (currentReasoningId) {
                                                controller.enqueue({ type: 'reasoning-end', id: currentReasoningId } as any);
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
                                                delta: message
                                            } as any);

                                            controller.enqueue({
                                                type: 'text-end',
                                                id: currentTextId
                                            } as any);
                                            currentTextId = null;

                                            if (kind === 'rate_limit') {
                                                controller.enqueue({
                                                    type: 'data-coordinator-followups',
                                                    data: {
                                                        question: message,
                                                        options: [
                                                            {
                                                                id: 'retry_same_request',
                                                                prompt: '同じ内容で再送する'
                                                            },
                                                            {
                                                                id: 'retry_with_shorter_scope',
                                                                prompt: '依頼範囲を短くして再送する'
                                                            },
                                                            {
                                                                id: 'retry_after_wait',
                                                                prompt: '30秒ほど待ってから再送する'
                                                            }
                                                        ]
                                                    }
                                                } as any);
                                            }
                                            break;
                                        }

                                        case 'on_custom_event': {
                                            const eventName = eventData.name;
                                            if (eventName?.startsWith('data-')) {
                                                const normalizedData =
                                                    eventName === 'data-plan_update'
                                                        ? normalizePlanUpdateData(eventData.data ?? {})
                                                        : (eventData.data ?? {});
                                                controller.enqueue({
                                                    type: eventName,
                                                    data: normalizedData
                                                } as any);
                                                break;
                                            }
                                            if (eventName === 'writer-output') {
                                                controller.enqueue({
                                                    type: 'data-writer-output',
                                                    data: eventData.data ?? {}
                                                } as any);
                                                break;
                                            }
                                            if (eventName === 'plan_update') {
                                                const normalized = normalizePlanUpdateData(eventData.data ?? {});
                                                controller.enqueue({
                                                    type: 'data-plan_update',
                                                    data: normalized
                                                } as any);
                                                break;
                                            }
                                            if (eventName === 'slide_outline_updated') {
                                                console.log("[Stream] Custom event 'slide_outline_updated' received.");
                                                // Backend slide_outline_updated is no longer used.
                                            } else if (eventName === 'title_generated') {
                                                console.log(`[Stream] Custom event 'title_generated' received: ${eventData.data?.title}`);
                                                // Forward title update to client
                                                controller.enqueue({
                                                    type: 'data-title-update',
                                                    data: { title: eventData.data?.title }
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
                                            const runName = meta.run_name || eventData.name || '';

                                            const isPlannerNode = node === 'planner' || (typeof checkpoint === 'string' && checkpoint.includes('planner:'));
                                            const isWriterNode = node === 'writer' || (typeof checkpoint === 'string' && checkpoint.includes('writer:'));
                                            const isCoordinatorNode = node === 'coordinator' || (typeof checkpoint === 'string' && checkpoint.includes('coordinator:'));
                                            const isSupervisorNode = node === 'supervisor' || (typeof checkpoint === 'string' && checkpoint.includes('supervisor:'));
                                            const isVisualizerNode = node === 'visualizer' || (typeof checkpoint === 'string' && checkpoint.includes('visualizer:'));
                                            const isAnalystNode = node === 'data_analyst' || (typeof checkpoint === 'string' && checkpoint.includes('data_analyst:'));

                                            const isWriterRun = runName === 'writer';
                                            const isPlannerOrWriter = runName === 'planner' || isWriterRun || isPlannerNode || isWriterNode;
                                            const isCoordinator = runName === 'coordinator' || isCoordinatorNode;
                                            const isSupervisorUserFacing = runName === 'supervisor';
                                            const isSupervisorInternal = (isSupervisorNode || runName.startsWith('supervisor_')) && !isSupervisorUserFacing;

                                            if (isResearcherSubgraph && (node === 'manager' || node === 'research_worker')) {
                                                break;
                                            }

                                            if (isVisualizerNode || isAnalystNode) {
                                                // These nodes emit structured JSON or thinking logs already handled via on_custom_event
                                                // or should be suppressed from the main chat text stream.
                                                break;
                                            }

                                            const runId = eventData.run_id;
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
                                                    if (part.type === 'thinking' && (part.thinking || part.text)) {
                                                        // Handling THINKING part (planner/writer only)
                                                        const reasoningContent = part.thinking || part.text;
                                                        if (isPlannerOrWriter) {
                                                            if (currentTextId) {
                                                                controller.enqueue({
                                                                    type: 'text-end',
                                                                    id: currentTextId
                                                                } as any);
                                                                currentTextId = null;
                                                            }

                                                            if (!currentReasoningId) {
                                                                currentReasoningId = uuidv4();
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
                                                        }
                                                    } else if ((part.type === 'text' || !part.type) && part.text) {
                                                        if (isPlannerOrWriter) {
                                                            if (runName === 'planner') {
                                                                plannerTextBuffer += part.text;
                                                            } else if (isWriterRun) {
                                                                writerTextBuffer += part.text;
                                                            }
                                                            continue;
                                                        }
                                                        if (isCoordinator) {
                                                            coordinatorTextBuffer += part.text;
                                                            emitCoordinatorResponseDeltaFromBuffer();
                                                            continue;
                                                        }
                                                        if (isSupervisorInternal) {
                                                            // Supervisor internal structured JSON must not appear in chat.
                                                            continue;
                                                        }

                                                        // Handling TEXT part (non-planner/writer)
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
                                                            delta: part.text
                                                        } as any);
                                                    }
                                                }
                                            } else if (typeof content === 'string' && content) {
                                                if (isPlannerOrWriter) {
                                                    if (runName === 'planner') {
                                                        plannerTextBuffer += content;
                                                    } else if (isWriterRun) {
                                                        writerTextBuffer += content;
                                                    }
                                                    break;
                                                }
                                                if (isCoordinator) {
                                                    coordinatorTextBuffer += content;
                                                    emitCoordinatorResponseDeltaFromBuffer();
                                                    break;
                                                }
                                                if (isSupervisorInternal) {
                                                    // Supervisor internal structured JSON must not appear in chat.
                                                    break;
                                                }

                                                // Fallback for simple string content (treat as text for other nodes)

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
                                                if (isPlannerOrWriter) {
                                                    if (runName === 'planner') {
                                                        const jsonText = extractFirstJson(plannerTextBuffer) || plannerTextBuffer;
                                                        try {
                                                            const parsed = JSON.parse(jsonText);
                                                            emitPlanFromParsed(parsed);
                                                        } catch (parseErr) {
                                                            console.error('[Stream] Planner JSON parse failed:', parseErr);
                                                            logToFile(`[${new Date().toISOString()}] [ParseError] planner JSON parse failed: ${String(parseErr)}\n`);
                                                        }
                                                        plannerTextBuffer = '';
                                                    } else if (isWriterRun) {
                                                        const jsonText = extractFirstJson(writerTextBuffer) || writerTextBuffer;
                                                        try {
                                                            const parsed = JSON.parse(jsonText);
                                                            emitOutlineFromParsed(parsed);
                                                        } catch (parseErr) {
                                                            console.error('[Stream] Writer JSON parse failed:', parseErr);
                                                            logToFile(`[${new Date().toISOString()}] [ParseError] writer JSON parse failed: ${String(parseErr)}\n`);
                                                        }
                                                        writerTextBuffer = '';
                                                    }
                                                }
                                                if (isCoordinator) {
                                                    const jsonText = extractFirstJson(coordinatorTextBuffer) || coordinatorTextBuffer;
                                                    try {
                                                        const parsed = JSON.parse(jsonText);
                                                        const responseText = parsed?.response ?? '';
                                                        const title = parsed?.title;
                                                        const followupOptions = normalizeCoordinatorFollowups(parsed?.followup_options);

                                                        if (currentReasoningId) {
                                                            controller.enqueue({ type: 'reasoning-end', id: currentReasoningId } as any);
                                                            currentReasoningId = null;
                                                        }

                                                        if (responseText && responseText.startsWith(coordinatorRenderedResponse)) {
                                                            const tailDelta = responseText.slice(coordinatorRenderedResponse.length);
                                                            if (tailDelta) {
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
                                                                    delta: tailDelta
                                                                } as any);
                                                            }
                                                            coordinatorRenderedResponse = responseText;
                                                        } else if (responseText && !coordinatorRenderedResponse) {
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
                                                                delta: responseText
                                                            } as any);
                                                            coordinatorRenderedResponse = responseText;
                                                        }

                                                        if (title) {
                                                            controller.enqueue({
                                                                type: 'data-title-update',
                                                                data: { title }
                                                            } as any);
                                                        }

                                                        if (followupOptions.length > 0) {
                                                            controller.enqueue({
                                                                type: 'data-coordinator-followups',
                                                                data: {
                                                                    question: responseText,
                                                                    options: followupOptions,
                                                                }
                                                            } as any);
                                                        }
                                                    } catch (parseErr) {
                                                        console.error('[Stream] Coordinator JSON parse failed:', parseErr);
                                                        logToFile(`[${new Date().toISOString()}] [ParseError] coordinator JSON parse failed: ${String(parseErr)}\n`);
                                                    }
                                                    coordinatorTextBuffer = '';
                                                    coordinatorRenderedResponse = '';
                                                    coordinatorResponseCompleted = false;
                                                }

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
