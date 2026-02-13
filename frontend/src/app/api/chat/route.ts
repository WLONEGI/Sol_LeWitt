import { NextRequest } from 'next/server';
import { v4 as uuidv4 } from 'uuid';
import { createUIMessageStreamResponse } from 'ai';
import { Agent } from 'undici';
import { normalizePlanUpdateData } from '@/features/chat/types/plan';

const CHAT_STREAM_TIMEOUT_SECONDS = 30 * 60;
const CHAT_STREAM_TIMEOUT_MS = CHAT_STREAM_TIMEOUT_SECONDS * 1000;

const BACKEND_STREAM_AGENT = new Agent({
    bodyTimeout: CHAT_STREAM_TIMEOUT_MS,
    headersTimeout: CHAT_STREAM_TIMEOUT_MS,
});

// Node.js runtime for long-running stream sessions.
export const runtime = 'nodejs';
export const maxDuration = CHAT_STREAM_TIMEOUT_SECONDS;

const ALLOWED_PRODUCT_TYPES = new Set(['slide', 'design', 'comic']);
const STREAM_BENCH_ENABLED_RAW = (process.env.STREAM_BENCH_ENABLED ?? '1').trim().toLowerCase();
const STREAM_BENCH_ENABLED = !['0', 'false', 'off', 'no'].includes(STREAM_BENCH_ENABLED_RAW);
const STREAM_BENCH_SAMPLE_RATE = (() => {
    const raw = Number(process.env.STREAM_BENCH_SAMPLE_RATE ?? '1');
    if (!Number.isFinite(raw)) return 1;
    return Math.max(0, Math.min(1, raw));
})();
const STREAM_UI_EVENT_FILTER_ENABLED_RAW = (process.env.STREAM_UI_EVENT_FILTER_ENABLED ?? '1').trim().toLowerCase();
const STREAM_UI_EVENT_FILTER_ENABLED = !['0', 'false', 'off', 'no'].includes(STREAM_UI_EVENT_FILTER_ENABLED_RAW);

const ALLOWED_DATA_CUSTOM_EVENTS = new Set([
    'data-plan_update',
    'data-plan_step_started',
    'data-plan_step_ended',
    'data-outline',
    'data-title-update',
    'data-coordinator-response',
    'data-coordinator-followups',
    'data-visual-plan',
    'data-visual-prompt',
    'data-visual-image',
    'data-visual-pdf',
    'data-analyst-start',
    'data-analyst-code-delta',
    'data-analyst-log-delta',
    'data-analyst-output',
    'data-analyst-complete',
    'data-writer-output',
    'data-research-start',
    'data-research-token',
    'data-research-complete',
    'data-research-report',
]);

const ALLOWED_LEGACY_CUSTOM_EVENTS = new Set([
    'plan_update',
    'writer-output',
    'title_generated',
    'research_worker_start',
    'research_worker_token',
    'research_worker_complete',
]);

const nowMs = () => performance.now();

const shouldCollectStreamBench = () => {
    if (!STREAM_BENCH_ENABLED) return false;
    if (STREAM_BENCH_SAMPLE_RATE >= 1) return true;
    if (STREAM_BENCH_SAMPLE_RATE <= 0) return false;
    return Math.random() <= STREAM_BENCH_SAMPLE_RATE;
};

const estimateTokensFromChars = (chars: number) => {
    if (chars <= 0) return 0;
    return Math.max(1, Math.round(chars / 4));
};

export async function POST(req: NextRequest) {
    try {
        const benchmarkEnabled = shouldCollectStreamBench();
        const routeStartMs = nowMs();

        const body = await req.json();
        const messages = Array.isArray(body?.messages) ? body.messages : [];
        const thread_id = body?.thread_id;
        const pptx_template_base64 = body?.pptx_template_base64;
        const selected_image_inputs = body?.selected_image_inputs;
        const attachments = body?.attachments;
        const interrupt_intent = body?.interrupt_intent;
        const product_type = body?.product_type;
        const aspect_ratio = body?.aspect_ratio;

        const authHeader = req.headers.get('authorization') || req.headers.get('Authorization');
        if (!authHeader || !authHeader.toLowerCase().startsWith('bearer ')) {
            return new Response(JSON.stringify({ error: 'Unauthorized' }), { status: 401 });
        }

        const lastMessage = messages[messages.length - 1] ?? {};
        const userContent =
            typeof lastMessage.content === 'string'
                ? lastMessage.content
                : (Array.isArray(lastMessage.parts)
                    ? lastMessage.parts
                        .filter((part: any) => part?.type === 'text' && typeof part?.text === 'string')
                        .map((part: any) => part.text)
                        .join('')
                    : '');

        const normalizedProductType =
            typeof product_type === 'string' && ALLOWED_PRODUCT_TYPES.has(product_type)
                ? product_type
                : undefined;

        const backendBody = {
            input: {
                messages: [{ role: 'user', content: userContent }],
                selected_image_inputs: Array.isArray(selected_image_inputs) ? selected_image_inputs : [],
                attachments: Array.isArray(attachments) ? attachments : [],
                interrupt_intent: Boolean(interrupt_intent),
                ...(normalizedProductType ? { product_type: normalizedProductType } : {}),
                ...(typeof aspect_ratio === 'string' && aspect_ratio ? { aspect_ratio } : {}),
                ...(pptx_template_base64 ? { pptx_template_base64 } : {}),
            },
            config: {
                configurable: { thread_id },
                recursion_limit: 50,
            },
        };

        const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000';
        const backendFetchStartMs = nowMs();
        const response = await fetch(`${BACKEND_URL}/api/chat/stream_events`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                Accept: 'text/event-stream',
                Authorization: authHeader,
                ...(thread_id ? { 'X-Thread-Id': thread_id } : {}),
            },
            body: JSON.stringify(backendBody),
            dispatcher: BACKEND_STREAM_AGENT,
        } as RequestInit & { dispatcher: Agent });
        const backendHeadersReceivedMs = nowMs();

        if (!response.ok) {
            const backendText = await response.text().catch(() => '');
            return new Response(
                JSON.stringify({
                    error: 'Backend error',
                    detail: backendText.slice(0, 1000),
                }),
                { status: response.status },
            );
        }

        if (!response.body) {
            return new Response(JSON.stringify({ error: 'No response body' }), { status: 500 });
        }

        return createUIMessageStreamResponse({
            headers: {
                'Cache-Control': 'no-cache, no-transform',
            },
            stream: new ReadableStream({
                async start(controller) {
                    const reader = response.body!.getReader();
                    const decoder = new TextDecoder();
                    const streamStartMs = nowMs();

                    let firstUpstreamChunkMs: number | null = null;
                    let firstSseEventMs: number | null = null;
                    let firstChatEventMs: number | null = null;
                    let firstUiTextDeltaMs: number | null = null;
                    let firstUiReasoningDeltaMs: number | null = null;

                    let totalSseEvents = 0;
                    let totalChatEvents = 0;
                    let totalCustomEvents = 0;
                    let totalUpstreamBytes = 0;
                    let totalUiTextChars = 0;
                    let totalUiReasoningChars = 0;

                    let sseBuffer = '';
                    let sseDataLines: string[] = [];

                    let currentReasoningId: string | null = null;
                    let currentTextId: string | null = null;

                    const closeReasoning = () => {
                        if (!currentReasoningId) return;
                        controller.enqueue({ type: 'reasoning-end', id: currentReasoningId } as any);
                        currentReasoningId = null;
                    };

                    const closeText = () => {
                        if (!currentTextId) return;
                        controller.enqueue({ type: 'text-end', id: currentTextId } as any);
                        currentTextId = null;
                    };

                    const ensureText = () => {
                        if (currentTextId) return;
                        currentTextId = uuidv4();
                        controller.enqueue({ type: 'text-start', id: currentTextId } as any);
                    };

                    const emitTextDelta = (delta: string) => {
                        if (!delta) return;
                        totalUiTextChars += delta.length;
                        if (firstUiTextDeltaMs === null) {
                            firstUiTextDeltaMs = nowMs();
                        }
                        closeReasoning();
                        ensureText();
                        controller.enqueue({
                            type: 'text-delta',
                            id: currentTextId!,
                            delta,
                        } as any);
                    };

                    const emitPlanUpdate = (data: unknown) => {
                        const normalized = normalizePlanUpdateData(data ?? {});
                        controller.enqueue({
                            type: 'data-plan_update',
                            data: normalized,
                        } as any);
                    };

                    const emitOutlineFromWriterOutput = (payload: Record<string, unknown>) => {
                        const output = payload.output;
                        const slides =
                            output && typeof output === 'object' && Array.isArray((output as any).slides)
                                ? (output as any).slides
                                : [];
                        if (!slides.length) return;
                        controller.enqueue({
                            type: 'data-outline',
                            data: {
                                slides,
                                ui_type: 'slide_outline',
                                title: 'Slide Outline',
                                description: 'The generated slide outline and narrative map.',
                            },
                        } as any);
                    };

                    const handleCustomEvent = (eventData: any) => {
                        const eventName = typeof eventData?.name === 'string' ? eventData.name : '';
                        const payload = eventData?.data ?? {};

                        if (!eventName) return;

                        const splitMessageBoundaryForUiEvent = () => {
                            // Force a new text/reasoning segment so that downstream data-* cards
                            // are rendered in the same temporal order they arrived.
                            closeText();
                            closeReasoning();
                        };

                        if (eventName.startsWith('data-')) {
                            if (STREAM_UI_EVENT_FILTER_ENABLED && !ALLOWED_DATA_CUSTOM_EVENTS.has(eventName)) {
                                return;
                            }
                            if (eventName === 'data-coordinator-response') {
                                splitMessageBoundaryForUiEvent();
                                const responseText = typeof payload?.response === 'string' ? payload.response : '';
                                if (responseText) emitTextDelta(responseText);
                                return;
                            }
                            if (eventName === 'data-plan_update') {
                                splitMessageBoundaryForUiEvent();
                                emitPlanUpdate(payload);
                                return;
                            }
                            splitMessageBoundaryForUiEvent();
                            controller.enqueue({
                                type: eventName,
                                data: payload,
                            } as any);
                            return;
                        }

                        if (STREAM_UI_EVENT_FILTER_ENABLED && !ALLOWED_LEGACY_CUSTOM_EVENTS.has(eventName)) {
                            return;
                        }

                        if (eventName === 'plan_update') {
                            splitMessageBoundaryForUiEvent();
                            emitPlanUpdate(payload);
                            return;
                        }

                        if (eventName === 'writer-output') {
                            splitMessageBoundaryForUiEvent();
                            const writerPayload = payload && typeof payload === 'object' ? payload : {};
                            controller.enqueue({
                                type: 'data-writer-output',
                                data: writerPayload,
                            } as any);

                            if ((writerPayload as any).artifact_type === 'outline') {
                                emitOutlineFromWriterOutput(writerPayload as Record<string, unknown>);
                            }
                            return;
                        }

                        if (eventName === 'title_generated') {
                            splitMessageBoundaryForUiEvent();
                            const title = typeof payload?.title === 'string' ? payload.title : '';
                            if (!title) return;
                            controller.enqueue({
                                type: 'data-title-update',
                                data: { title },
                            } as any);
                            return;
                        }

                        if (eventName === 'research_worker_start') {
                            splitMessageBoundaryForUiEvent();
                            controller.enqueue({ type: 'data-research-start', data: payload } as any);
                            return;
                        }
                        if (eventName === 'research_worker_token') {
                            controller.enqueue({ type: 'data-research-token', data: payload } as any);
                            return;
                        }
                        if (eventName === 'research_worker_complete') {
                            splitMessageBoundaryForUiEvent();
                            controller.enqueue({ type: 'data-research-complete', data: payload } as any);
                        }
                    };

                    const handleChatModelStream = (eventData: any) => {
                        const metadata = eventData?.metadata ?? {};
                        const node =
                            typeof metadata?.langgraph_node === 'string'
                                ? metadata.langgraph_node
                                : '';
                        const checkpoint =
                            typeof metadata?.langgraph_checkpoint_ns === 'string'
                                ? metadata.langgraph_checkpoint_ns
                                : (typeof metadata?.checkpoint_ns === 'string' ? metadata.checkpoint_ns : '');
                        const eventName =
                            typeof eventData?.name === 'string'
                                ? eventData.name
                                : '';
                        const runName =
                            typeof metadata?.run_name === 'string'
                                ? metadata.run_name
                                : eventName;

                        const isPlannerOrWriter =
                            runName === 'planner'
                            || runName === 'writer'
                            || eventName === 'planner'
                            || eventName === 'writer'
                            || node === 'planner'
                            || node === 'writer'
                            || checkpoint.includes('planner:')
                            || checkpoint.includes('writer:');
                        const isSupervisorUserFacing =
                            runName === 'supervisor'
                            || eventName === 'supervisor';
                        const isSupervisorInternal =
                            (
                                node === 'supervisor'
                                || runName.startsWith('supervisor_')
                                || eventName.startsWith('supervisor_')
                                || checkpoint.includes('supervisor:')
                            ) && !isSupervisorUserFacing;

                        const chunk = eventData?.data?.chunk;
                        const isLastChunk = chunk?.chunk_position === 'last';
                        const content =
                            chunk && typeof chunk === 'object' && 'content' in chunk
                                ? chunk.content
                                : (typeof chunk === 'string' ? chunk : '');

                        const handleReasoningDelta = (delta: string) => {
                            if (!delta || !isPlannerOrWriter) return;
                            totalUiReasoningChars += delta.length;
                            if (firstUiReasoningDeltaMs === null) {
                                firstUiReasoningDeltaMs = nowMs();
                            }
                            closeText();
                            if (!currentReasoningId) {
                                currentReasoningId = uuidv4();
                                controller.enqueue({ type: 'reasoning-start', id: currentReasoningId } as any);
                            }
                            controller.enqueue({
                                type: 'reasoning-delta',
                                id: currentReasoningId,
                                delta,
                            } as any);
                        };

                        const handleTextDelta = (delta: string) => {
                            if (!delta) return;
                            if (isPlannerOrWriter) return;
                            if (isSupervisorInternal) return;
                            emitTextDelta(delta);
                        };

                        if (Array.isArray(content)) {
                            for (const part of content) {
                                if (!part) continue;
                                if (typeof part === 'string') {
                                    handleTextDelta(part);
                                    continue;
                                }
                                if (typeof part !== 'object') continue;

                                const partType = typeof (part as any).type === 'string' ? (part as any).type : '';
                                let thinkingText = '';
                                if (typeof (part as any).thinking === 'string') {
                                    thinkingText = (part as any).thinking;
                                } else if (typeof (part as any).reasoning === 'string') {
                                    thinkingText = (part as any).reasoning;
                                } else if (
                                    typeof (part as any).text === 'string' &&
                                    (partType === 'thinking' || partType === 'reasoning')
                                ) {
                                    thinkingText = (part as any).text;
                                }

                                if (thinkingText) {
                                    handleReasoningDelta(thinkingText);
                                    continue;
                                }

                                const text =
                                    typeof (part as any).text === 'string'
                                        ? (part as any).text
                                        : '';
                                if (text) handleTextDelta(text);
                            }
                        } else if (typeof content === 'string' && content) {
                            handleTextDelta(content);
                        }

                        if (isLastChunk) {
                            closeText();
                            closeReasoning();
                        }
                    };

                    const processSsePayload = (rawPayload: string) => {
                        if (!rawPayload) return;
                        try {
                            const eventData = JSON.parse(rawPayload);
                            const eventType = eventData?.event;
                            totalSseEvents += 1;
                            if (firstSseEventMs === null) {
                                firstSseEventMs = nowMs();
                            }
                            if (eventType === 'on_custom_event') {
                                totalCustomEvents += 1;
                                handleCustomEvent(eventData);
                                return;
                            }
                            if (eventType === 'on_chat_model_stream') {
                                totalChatEvents += 1;
                                if (firstChatEventMs === null) {
                                    firstChatEventMs = nowMs();
                                }
                                handleChatModelStream(eventData);
                                return;
                            }
                            if (eventType === 'error') {
                                const payload = eventData?.data;
                                const kind = typeof payload?.kind === 'string' ? payload.kind : '';
                                const message =
                                    typeof payload?.message === 'string' && payload.message.trim().length > 0
                                        ? payload.message
                                        : (typeof payload === 'string' ? payload : '処理中にエラーが発生しました。');

                                closeReasoning();
                                ensureText();
                                controller.enqueue({
                                    type: 'text-delta',
                                    id: currentTextId!,
                                    delta: message,
                                } as any);
                                closeText();

                                if (kind === 'rate_limit') {
                                    controller.enqueue({
                                        type: 'data-coordinator-followups',
                                        data: {
                                            question: message,
                                            options: [
                                                { id: 'retry_same_request', prompt: '同じ内容で再送する' },
                                                { id: 'retry_with_shorter_scope', prompt: '依頼範囲を短くして再送する' },
                                                { id: 'retry_after_wait', prompt: '30秒ほど待ってから再送する' },
                                            ],
                                        },
                                    } as any);
                                }
                            }
                        } catch {
                            // Ignore malformed SSE payload from upstream.
                        }
                    };

                    try {
                        while (true) {
                            const { done, value } = await reader.read();
                            if (done) break;
                            if (firstUpstreamChunkMs === null) {
                                firstUpstreamChunkMs = nowMs();
                            }
                            totalUpstreamBytes += value.byteLength;

                            sseBuffer += decoder.decode(value, { stream: true });

                            let newlineIndex = sseBuffer.indexOf('\n');
                            while (newlineIndex >= 0) {
                                const rawLine = sseBuffer.slice(0, newlineIndex).replace(/\r$/, '');
                                sseBuffer = sseBuffer.slice(newlineIndex + 1);

                                if (!rawLine) {
                                    if (sseDataLines.length > 0) {
                                        processSsePayload(sseDataLines.join('\n'));
                                        sseDataLines = [];
                                    }
                                } else if (!rawLine.startsWith(':') && rawLine.startsWith('data:')) {
                                    sseDataLines.push(rawLine.slice(5).trimStart());
                                }

                                newlineIndex = sseBuffer.indexOf('\n');
                            }
                        }

                        const tail = decoder.decode();
                        if (tail) sseBuffer += tail;

                        if (sseBuffer.trim().startsWith('data:')) {
                            sseDataLines.push(sseBuffer.replace(/^data:\s*/, ''));
                        }
                        if (sseDataLines.length > 0) {
                            processSsePayload(sseDataLines.join('\n'));
                        }

                        closeText();
                        closeReasoning();
                    } catch (error) {
                        controller.error(error);
                    } finally {
                        if (benchmarkEnabled) {
                            const streamEndMs = nowMs();
                            const textTokensEst = estimateTokensFromChars(totalUiTextChars);
                            const reasoningTokensEst = estimateTokensFromChars(totalUiReasoningChars);
                            const totalTokensEst = textTokensEst + reasoningTokensEst;

                            const generationWindowSec =
                                firstUiTextDeltaMs !== null
                                    ? Math.max((streamEndMs - firstUiTextDeltaMs) / 1000, 1e-6)
                                    : null;
                            const tokensPerSec = generationWindowSec
                                ? Number((totalTokensEst / generationWindowSec).toFixed(2))
                                : null;

                            console.log(
                                '[STREAM_BENCH][frontend]',
                                JSON.stringify({
                                    thread_id: thread_id ?? null,
                                    product_type: normalizedProductType ?? null,
                                    fetch_headers_ms: Number((backendHeadersReceivedMs - backendFetchStartMs).toFixed(2)),
                                    upstream_first_chunk_ms: firstUpstreamChunkMs === null
                                        ? null
                                        : Number((firstUpstreamChunkMs - backendFetchStartMs).toFixed(2)),
                                    first_sse_event_ms: firstSseEventMs === null
                                        ? null
                                        : Number((firstSseEventMs - routeStartMs).toFixed(2)),
                                    first_chat_event_ms: firstChatEventMs === null
                                        ? null
                                        : Number((firstChatEventMs - routeStartMs).toFixed(2)),
                                    ttft_ms: firstUiTextDeltaMs === null
                                        ? null
                                        : Number((firstUiTextDeltaMs - routeStartMs).toFixed(2)),
                                    first_reasoning_ms: firstUiReasoningDeltaMs === null
                                        ? null
                                        : Number((firstUiReasoningDeltaMs - routeStartMs).toFixed(2)),
                                    bff_stream_setup_ms: Number((streamStartMs - routeStartMs).toFixed(2)),
                                    total_stream_ms: Number((streamEndMs - routeStartMs).toFixed(2)),
                                    stream_window_ms: firstUiTextDeltaMs === null
                                        ? null
                                        : Number((streamEndMs - firstUiTextDeltaMs).toFixed(2)),
                                    sse_events: totalSseEvents,
                                    chat_events: totalChatEvents,
                                    custom_events: totalCustomEvents,
                                    upstream_bytes: totalUpstreamBytes,
                                    ui_text_chars: totalUiTextChars,
                                    ui_reasoning_chars: totalUiReasoningChars,
                                    text_tokens_est: textTokensEst,
                                    reasoning_tokens_est: reasoningTokensEst,
                                    tokens_est_total: totalTokensEst,
                                    tokens_est_per_sec: tokensPerSec,
                                }),
                            );
                        }

                        try {
                            controller.close();
                        } catch {
                            // no-op
                        }
                    }
                },
            }),
        });
    } catch (error: any) {
        return new Response(JSON.stringify({ error: error?.message || 'Unknown error' }), { status: 500 });
    }
}
