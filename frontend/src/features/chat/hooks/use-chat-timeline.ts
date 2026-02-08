"use client"

import { useMemo } from 'react'
import type { UIMessage } from 'ai'
import { TimelineEvent, MessageTimelineItem, ResearchReportTimelineItem } from "../types/timeline"
import type { PlanUpdateData } from "../types/plan"
import { normalizePlanUpdateData } from "../types/plan"

/**
 * Extracts text content from UIMessage parts array
 */
function getTextFromParts(parts: UIMessage['parts']): string {
    if (!parts) return ''
    return parts
        .filter((p): p is { type: 'text'; text: string } => p.type === 'text')
        .map(p => p.text)
        .join('')
}

/**
 * Extracts reasoning content from UIMessage parts array
 */
function getReasoningFromParts(parts: UIMessage['parts']): string | undefined {
    if (!parts) return undefined
    const reasoning = parts
        .filter((p): p is { type: 'reasoning'; text: string; details?: any } => p.type === 'reasoning')
        .map(p => p.text)
        .join('\n')

    return reasoning.length > 0 ? reasoning : undefined
}

/**
 * Simplified chat timeline hook.
 * Processes only standard chat messages (no custom events).
 */
export function useChatTimeline(
    messages: UIMessage[] = [],
    data: any[] | undefined = [],
    _threadId?: string | null
) {
    const MESSAGE_ORDER_UNIT = 1000

    // Keep data-event ordering stable by using emit-time metadata from chat-interface.
    // This prevents step markers from jumping when message count changes later.
    const getDataEventTimestamp = (event: any, fallbackIndex: number) => {
        const rawMsgCount = event?.__msgCount
        const msgCountAtEmit =
            typeof rawMsgCount === 'number' && Number.isFinite(rawMsgCount)
                ? rawMsgCount
                : messages.length

        const rawSeq = event?.__seq
        const seq =
            typeof rawSeq === 'number' && Number.isFinite(rawSeq)
                ? rawSeq
                : fallbackIndex

        return msgCountAtEmit * MESSAGE_ORDER_UNIT - 0.5 + (seq / 1_000_000)
    }

    // Extract the latest plan from data stream
    const latestPlan = useMemo(() => {
        if (!data || data.length === 0) return null as PlanUpdateData | null;

        // Find the latest plan_update
        for (let i = data.length - 1; i >= 0; i--) {
            const event = data[i];
            if (event && typeof event === 'object' && event.type === 'data-plan_update') {
                return normalizePlanUpdateData(event.data);
            }
        }
        return null as PlanUpdateData | null;
    }, [data])

    // Convert messages to timeline items
    const timeline = useMemo<TimelineEvent[]>(() => {
        const items: TimelineEvent[] = [];

        messages.forEach((msg, msgIndex) => {
            const messageId = `msg-${msg.id}`;
            const baseTimestamp = msgIndex * MESSAGE_ORDER_UNIT;

            // Track if we added any items for this message
            const beforeLength = items.length;

            // Process parts while avoiding empty/fragmented message items.
            if (msg.parts && msg.parts.length > 0) {
                let textBuffer = '';
                let textStartIndex = -1;
                let reasoningBuffer = '';
                let reasoningStartIndex = -1;

                const flushText = (indexFallback: number) => {
                    if (!textBuffer.trim()) {
                        textBuffer = '';
                        textStartIndex = -1;
                        return;
                    }

                    const logicalIndex = textStartIndex >= 0 ? textStartIndex : indexFallback
                    const timestamp = baseTimestamp + logicalIndex;
                    items.push({
                        id: `${messageId}-text-${logicalIndex}`,
                        type: 'message',
                        timestamp,
                        message: {
                            id: msg.id,
                            role: msg.role,
                            content: textBuffer,
                            parts: [{ type: 'text', text: textBuffer }],
                            toolInvocations: (msg as any).toolInvocations,
                        } as any
                    });

                    textBuffer = '';
                    textStartIndex = -1;
                };

                const flushReasoning = (indexFallback: number) => {
                    if (!reasoningBuffer.trim()) {
                        reasoningBuffer = '';
                        reasoningStartIndex = -1;
                        return;
                    }

                    const logicalIndex = reasoningStartIndex >= 0 ? reasoningStartIndex : indexFallback
                    const timestamp = baseTimestamp + logicalIndex;
                    items.push({
                        id: `${messageId}-reasoning-${logicalIndex}`,
                        type: 'message',
                        timestamp,
                        message: {
                            id: msg.id,
                            role: msg.role,
                            content: '',
                            reasoning: reasoningBuffer,
                            parts: [{ type: 'reasoning', text: reasoningBuffer }],
                        } as any
                    });

                    reasoningBuffer = '';
                    reasoningStartIndex = -1;
                };

                msg.parts.forEach((part, partIndex) => {
                    const partId = `${messageId}-part-${partIndex}`;
                    const p = part as any;

                    if (p.type === 'text') {
                        flushReasoning(partIndex);

                        const chunk = typeof p.text === 'string' ? p.text : '';
                        if (!chunk) return;

                        if (!chunk.trim() && textBuffer.length === 0) {
                            return;
                        }

                        if (textStartIndex < 0) {
                            textStartIndex = partIndex;
                        }
                        textBuffer += chunk;
                        return;
                    }

                    if (p.type === 'reasoning') {
                        flushText(partIndex);

                        const chunk = typeof p.text === 'string' ? p.text : '';
                        if (!chunk) return;

                        if (!chunk.trim() && reasoningBuffer.length === 0) {
                            return;
                        }

                        if (reasoningStartIndex < 0) {
                            reasoningStartIndex = partIndex;
                        }
                        reasoningBuffer += chunk;
                        return;
                    }

                    flushText(partIndex);
                    flushReasoning(partIndex);

                    if (typeof p.type === 'string' && p.type.startsWith('data-')) {
                        const eventData = p.data;
                        if (eventData && typeof eventData === 'object') {
                            if (p.type === 'data-research-start') {
                                items.push({
                                    id: `${partId}-research-${eventData.task_id}`,
                                    type: 'research_report',
                                    timestamp: baseTimestamp + partIndex,
                                    taskId: eventData.task_id.toString(),
                                    perspective: eventData.perspective,
                                    status: 'running'
                                });
                            } else if (p.type === 'data-research-complete') {
                                const startItem = items.find(
                                    item => item.type === 'research_report' && item.taskId === eventData.task_id.toString()
                                ) as ResearchReportTimelineItem | undefined;

                                if (startItem) {
                                    startItem.status = 'completed';
                                }
                            }
                        }
                    }
                });

                flushText(msg.parts.length);
                flushReasoning(msg.parts.length);
            }

            // Fallback: if we have parts but added nothing, OR if we have no parts
            const itemsAddedForMessage = items.length - beforeLength;
            if (itemsAddedForMessage === 0) {
                const content = (msg as any).content || '';
                // Add message if there's content or if it's a user message (user messages should always be visible)
                if (content || msg.role === 'user') {
                    items.push({
                        id: messageId,
                        type: 'message',
                        timestamp: baseTimestamp,
                        message: {
                            id: msg.id,
                            role: msg.role,
                            content: content,
                            toolInvocations: (msg as any).toolInvocations,
                        } as any
                    });
                }
            }
        });

        // Data events from stream
        if (data && data.length > 0) {
            const analystMap = new Map<string, { item: any; lastTimestamp: number }>();
            const outlineMap = new Map<string, { item: TimelineEvent; lastTimestamp: number }>();
            const writerArtifactMap = new Map<string, { item: TimelineEvent; lastTimestamp: number }>();
            const imageSearchMap = new Map<string, { item: TimelineEvent; lastTimestamp: number }>();

            data.forEach((event, idx) => {
                if (!event || typeof event !== 'object') return;
                const type = event.type as string;
                const payload = (event as any).data || {};
                const timestamp = getDataEventTimestamp(event, idx);

                // 0. Planner step start -> inject a bold chat line
                if (type === 'data-plan_step_started') {
                    const stepTitle = typeof payload.title === 'string' ? payload.title.trim() : '';
                    if (!stepTitle) return;

                    // Use the natural timestamp from the event
                    // This ensures plan steps appear in the order they were generated
                    items.push({
                        id: `plan-step-start-${idx}`,
                        type: 'plan_step_marker',
                        timestamp,
                        stepId: String(payload.step_id ?? idx),
                        title: stepTitle,
                    });
                    return;
                }

                if (type === 'data-plan_step_ended') {
                    items.push({
                        id: `plan-step-end-${idx}`,
                        type: 'plan_step_end_marker',
                        timestamp,
                        stepId: String(payload.step_id ?? idx),
                    });
                    return;
                }

                // 1. Data Analyst
                if (type.startsWith('data-analyst-')) {
                    const artifactId = payload.artifact_id || 'data_analyst';
                    const existing = analystMap.get(artifactId);
                    if (existing) {
                        existing.lastTimestamp = timestamp;
                        if (payload.title) existing.item.title = payload.title;
                        return;
                    }

                    analystMap.set(artifactId, {
                        item: {
                            id: `data-analyst-${artifactId}`,
                            type: 'artifact',
                            timestamp,
                            artifactId,
                            title: payload.title || 'Data Analyst',
                            icon: 'BarChart'
                        },
                        lastTimestamp: timestamp
                    });
                }

                // 2. Slide Outline (keep one per artifact, with latest state)
                else if (type === 'data-outline') {
                    const artifactId = typeof payload.artifact_id === 'string' ? payload.artifact_id : '';
                    const mapKey = artifactId.trim().length > 0 ? `artifact:${artifactId}` : 'default';
                    const existing = outlineMap.get(mapKey);

                    if (existing) {
                        existing.lastTimestamp = timestamp;
                        existing.item = {
                            ...(existing.item as any),
                            timestamp,
                            slides: Array.isArray(payload.slides) ? payload.slides : [],
                            title: payload.title || 'Slide Outline',
                        } as TimelineEvent;
                        return;
                    }

                    outlineMap.set(mapKey, {
                        item: {
                            id: `outline-${mapKey}`,
                            type: 'slide_outline',
                            timestamp,
                            slides: Array.isArray(payload.slides) ? payload.slides : [],
                            title: payload.title || 'Slide Outline',
                        } as TimelineEvent,
                        lastTimestamp: timestamp,
                    });
                    return;
                }

                // 3. Visual image result
                else if (type === 'data-visual-image') {
                    // Suppress per-image timeline cards to reduce cognitive load.
                    // A unified slide deck UI is rendered from `latestSlideDeck`.
                    return;
                }

                // 4. Image Search results
                else if (type === 'data-image-search-results') {
                    const candidates = Array.isArray(payload.candidates) ? payload.candidates : [];
                    const artifactId = typeof payload.artifact_id === 'string' ? payload.artifact_id : undefined;
                    const taskId = String(payload.task_id ?? idx);
                    const query = typeof payload.query === 'string' ? payload.query : '';
                    const mapKey = artifactId?.trim()
                        ? `artifact:${artifactId}`
                        : `task:${taskId}`;
                    const existing = imageSearchMap.get(mapKey);

                    if (existing) {
                        existing.lastTimestamp = timestamp;
                        existing.item = {
                            ...(existing.item as any),
                            timestamp,
                            taskId,
                            artifactId,
                            query,
                            perspective: typeof payload.perspective === 'string' ? payload.perspective : undefined,
                            candidates,
                        } as any;
                        return;
                    }

                    imageSearchMap.set(mapKey, {
                        item: {
                            id: `image-search-${mapKey}`,
                            type: 'image_search_results',
                            timestamp,
                            taskId,
                            artifactId,
                            query,
                            perspective: typeof payload.perspective === 'string' ? payload.perspective : undefined,
                            candidates,
                        } as any,
                        lastTimestamp: timestamp,
                    });
                    return;
                }

                // 5. Writer outputs (keep one per artifact, with latest state)
                else if (type === 'data-writer-output') {
                    const artifactType = typeof payload.artifact_type === 'string' ? payload.artifact_type : 'report';
                    if (artifactType === 'outline') return;

                    const artifactId = payload.artifact_id || `writer-${idx}`;
                    const existing = writerArtifactMap.get(artifactId);
                    if (existing) {
                        existing.lastTimestamp = timestamp;
                        existing.item = {
                            ...(existing.item as any),
                            timestamp,
                            artifactId,
                            title: payload.title || 'Writer Output',
                            icon: 'BookOpen',
                            kind: artifactType,
                        } as any;
                        return;
                    }

                    writerArtifactMap.set(artifactId, {
                        item: {
                            id: `writer-${artifactId}`,
                            type: 'artifact',
                            timestamp,
                            artifactId,
                            title: payload.title || 'Writer Output',
                            icon: 'BookOpen',
                            kind: artifactType,
                        } as any,
                        lastTimestamp: timestamp,
                    });
                    return;
                }
            });

            analystMap.forEach(({ item, lastTimestamp }) => {
                item.timestamp = lastTimestamp;
                items.push(item);
            });
            outlineMap.forEach(({ item, lastTimestamp }) => {
                item.timestamp = lastTimestamp;
                items.push(item);
            });
            imageSearchMap.forEach(({ item, lastTimestamp }) => {
                item.timestamp = lastTimestamp;
                items.push(item);
            });
            writerArtifactMap.forEach(({ item, lastTimestamp }) => {
                item.timestamp = lastTimestamp;
                items.push(item);
            });
        }


        // Add any remaining research events from the global data stream that might not be in parts
        // (This is a safety net for other custom events like plan_update or data-outline)
        return items.sort((a, b) => {
            if (a.timestamp !== b.timestamp) return a.timestamp - b.timestamp;
            return a.id.localeCompare(b.id);
        });
    }, [messages, data])

    // Extract the latest slide outline from data stream
    const latestOutline = useMemo(() => {
        if (!data || data.length === 0) return null;

        // Find the latest data-outline
        for (let i = data.length - 1; i >= 0; i--) {
            const event = data[i];
            if (event && typeof event === 'object' && event.type === 'data-outline') {
                return event.data;
            }
        }
        return null;
    }, [data])

    const latestSlideDeck = useMemo(() => {
        if (!data || data.length === 0) return null;

        let deck: any = null;
        const slidesMap = new Map<number, any>();

        for (const event of data) {
            if (!event || typeof event !== 'object') continue;
            const type = event.type as string;
            if (!type || !type.startsWith('data-visual-')) continue;

            const payload = event.data || {};
            const artifactId = payload.artifact_id || deck?.artifactId || 'visual_deck';

            if (!deck || deck.artifactId !== artifactId) {
                deck = {
                    artifactId,
                    title: payload.deck_title || payload.title || deck?.title || 'Generated Slides',
                    slides: [],
                    status: 'streaming',
                    pdf_url: payload.pdf_url,
                };
            }

            if (payload.slide_number) {
                const existing = slidesMap.get(payload.slide_number) || { slide_number: payload.slide_number };
                slidesMap.set(payload.slide_number, {
                    ...existing,
                    title: payload.title ?? existing.title,
                    image_url: payload.image_url ?? existing.image_url,
                    prompt_text: payload.prompt_text ?? existing.prompt_text,
                    structured_prompt: payload.structured_prompt ?? existing.structured_prompt,
                    rationale: payload.rationale ?? existing.rationale,
                    layout_type: payload.layout_type ?? existing.layout_type,
                    selected_inputs: payload.selected_inputs ?? existing.selected_inputs,
                    status: payload.status ?? existing.status,
                });
            }

            if (payload.pdf_url) {
                deck.pdf_url = payload.pdf_url;
            }
        }

        if (deck) {
            deck.slides = Array.from(slidesMap.values()).sort((a, b) => a.slide_number - b.slide_number);
            const allReady = deck.slides.length > 0 && deck.slides.every((s: any) => Boolean(s.image_url));
            deck.status = allReady ? 'completed' : 'streaming';
        }

        return deck;
    }, [data])

    return { timeline, latestPlan, latestOutline, latestSlideDeck }
}
