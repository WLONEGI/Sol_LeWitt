"use client"

import { useMemo } from 'react'
import type { UIMessage } from 'ai'
import { TimelineEvent, MessageTimelineItem, ResearchReportTimelineItem } from "../types/timeline"
import type { PlanUpdateData } from "../types/plan"
import { normalizePlanUpdateData } from "../types/plan"
import {
    CHARACTER_SHEET_BUNDLE_ARTIFACT_ID,
    inferVisualizerModeFromPayload,
} from "@/features/preview/lib/character-sheet-bundle"

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

        if (event?.type === 'data-coordinator-followups') {
            return msgCountAtEmit * MESSAGE_ORDER_UNIT + 999 + (seq / 1_000_000)
        }

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
        const analystMap = new Map<string, { item: any; lastTimestamp: number }>();
        const outlineMap = new Map<string, { item: TimelineEvent; lastTimestamp: number }>();
        const writerArtifactMap = new Map<string, { item: TimelineEvent; lastTimestamp: number }>();
        const visualDeckMap = new Map<
            string,
            { item: TimelineEvent; lastTimestamp: number; slidesMap: Map<number, any> }
        >();
        const researchMap = new Map<string, ResearchReportTimelineItem>();

        const ingestStructuredEvent = (
            type: string,
            payload: any,
            timestamp: number,
            idSeed: string
        ) => {
            const eventPayload = payload && typeof payload === 'object' ? payload : {};

            if (type === 'data-plan_step_started') {
                const stepTitle = typeof eventPayload.title === 'string' ? eventPayload.title.trim() : '';
                if (!stepTitle) return;
                items.push({
                    id: `${idSeed}-plan-step-start-${String(eventPayload.step_id ?? 'unknown')}`,
                    type: 'plan_step_marker',
                    timestamp,
                    stepId: String(eventPayload.step_id ?? idSeed),
                    title: stepTitle,
                });
                return;
            }

            if (type === 'data-plan_step_ended') {
                items.push({
                    id: `${idSeed}-plan-step-end-${String(eventPayload.step_id ?? 'unknown')}`,
                    type: 'plan_step_end_marker',
                    timestamp,
                    stepId: String(eventPayload.step_id ?? idSeed),
                });
                return;
            }

            if (type === 'data-research-start') {
                const taskId = String(eventPayload.task_id ?? idSeed);
                const nextItem: ResearchReportTimelineItem = {
                    id: `${idSeed}-research-${taskId}`,
                    type: 'research_report',
                    timestamp,
                    taskId,
                    perspective: typeof eventPayload.perspective === 'string' ? eventPayload.perspective : '',
                    status: 'running',
                    searchMode: typeof eventPayload.search_mode === 'string' ? eventPayload.search_mode : undefined,
                };
                researchMap.set(taskId, nextItem);
                items.push(nextItem);
                return;
            }

            if (type === 'data-research-report') {
                const taskId = String(eventPayload.task_id ?? idSeed);
                const statusValue = typeof eventPayload.status === 'string' ? eventPayload.status : 'completed';
                const normalizedStatus: 'running' | 'completed' | 'failed' =
                    statusValue === 'failed' ? 'failed' : statusValue === 'running' ? 'running' : 'completed';
                const reportText = typeof eventPayload.report === 'string' ? eventPayload.report : '';
                const sources = Array.isArray(eventPayload.sources)
                    ? eventPayload.sources.filter((source: any) => typeof source === 'string')
                    : [];
                const searchMode = typeof eventPayload.search_mode === 'string' ? eventPayload.search_mode : undefined;
                const perspective = typeof eventPayload.perspective === 'string' ? eventPayload.perspective : '';

                const existing = researchMap.get(taskId);
                if (existing) {
                    existing.timestamp = timestamp;
                    if (perspective) existing.perspective = perspective;
                    existing.status = normalizedStatus;
                    if (searchMode) existing.searchMode = searchMode;
                    if (reportText) existing.report = reportText;
                    existing.sources = sources;
                    return;
                }

                const nextItem: ResearchReportTimelineItem = {
                    id: `${idSeed}-research-${taskId}`,
                    type: 'research_report',
                    timestamp,
                    taskId,
                    perspective,
                    status: normalizedStatus,
                    searchMode,
                    report: reportText,
                    sources,
                };
                researchMap.set(taskId, nextItem);
                items.push(nextItem);
                return;
            }

            if (type === 'data-research-complete') {
                const taskId = String(eventPayload.task_id ?? idSeed);
                const startItem = researchMap.get(taskId);
                if (startItem) {
                    if (startItem.status !== 'failed') {
                        startItem.status = 'completed';
                    }
                }
                return;
            }

            if (type.startsWith('data-analyst-')) {
                const artifactId = eventPayload.artifact_id || 'data_analyst';
                const existing = analystMap.get(artifactId);
                const nextStatus =
                    typeof eventPayload.status === 'string' && eventPayload.status.trim().length > 0
                        ? eventPayload.status.trim()
                        : (type === 'data-analyst-complete' ? 'completed' : 'running');
                if (existing) {
                    existing.lastTimestamp = timestamp;
                    if (eventPayload.title) existing.item.title = eventPayload.title;
                    (existing.item as any).status = nextStatus;
                    (existing.item as any).kind = 'data_analyst';
                    return;
                }

                analystMap.set(artifactId, {
                    item: {
                        id: `data-analyst-${artifactId}`,
                        type: 'artifact',
                        timestamp,
                        artifactId,
                        title: eventPayload.title || 'Data Analyst',
                        icon: 'BarChart',
                        kind: 'data_analyst',
                        status: nextStatus,
                    },
                    lastTimestamp: timestamp
                });
                return;
            }

            if (type === 'data-outline') {
                const artifactId = typeof eventPayload.artifact_id === 'string' ? eventPayload.artifact_id : '';
                const mapKey = artifactId.trim().length > 0 ? `artifact:${artifactId}` : 'default';
                const existing = outlineMap.get(mapKey);

                if (existing) {
                    existing.lastTimestamp = timestamp;
                    existing.item = {
                        ...(existing.item as any),
                        timestamp,
                        slides: Array.isArray(eventPayload.slides) ? eventPayload.slides : [],
                        title: eventPayload.title || 'Slide Outline',
                    } as TimelineEvent;
                    return;
                }

                outlineMap.set(mapKey, {
                    item: {
                        id: `outline-${mapKey}`,
                        type: 'slide_outline',
                        timestamp,
                        slides: Array.isArray(eventPayload.slides) ? eventPayload.slides : [],
                        title: eventPayload.title || 'Slide Outline',
                    } as TimelineEvent,
                    lastTimestamp: timestamp,
                });
                return;
            }

            if (type.startsWith('data-visual-')) {
                const baseArtifactId =
                    typeof eventPayload.artifact_id === 'string' && eventPayload.artifact_id.trim().length > 0
                        ? eventPayload.artifact_id.trim()
                        : 'visual_deck';

                const existing = visualDeckMap.get(baseArtifactId);
                const previousMode =
                    existing && typeof (existing.item as any).mode === 'string'
                        ? (existing.item as any).mode
                        : null;
                const inferredMode = inferVisualizerModeFromPayload(eventPayload, previousMode);
                const deckKind =
                    inferredMode === 'character_sheet_render'
                        ? 'character_sheet_deck'
                        : inferredMode === 'comic_page_render'
                            ? 'comic_page_deck'
                            : 'slide_deck';

                const readAspectRatio = (payload: any): string | undefined => {
                    if (!payload || typeof payload !== 'object') return undefined;
                    if (typeof payload.aspect_ratio === 'string' && payload.aspect_ratio.trim().length > 0) {
                        return payload.aspect_ratio.trim();
                    }
                    if (
                        payload.metadata &&
                        typeof payload.metadata === 'object' &&
                        typeof payload.metadata.aspect_ratio === 'string' &&
                        payload.metadata.aspect_ratio.trim().length > 0
                    ) {
                        return payload.metadata.aspect_ratio.trim();
                    }
                    return undefined;
                };

                if (existing) {
                    existing.lastTimestamp = timestamp;
                    const item = existing.item as any;
                    item.kind = deckKind;
                    if (inferredMode) item.mode = inferredMode;
                    const nextTitle =
                        (typeof eventPayload.deck_title === 'string' && eventPayload.deck_title.trim().length > 0)
                            ? eventPayload.deck_title.trim()
                            : (typeof eventPayload.title === 'string' && eventPayload.title.trim().length > 0)
                                ? eventPayload.title.trim()
                                : item.title;
                    if (nextTitle) item.title = nextTitle;

                    const nextAspectRatio = readAspectRatio(eventPayload);
                    if (nextAspectRatio) item.aspectRatio = nextAspectRatio;

                    if (typeof eventPayload.pdf_url === 'string' && eventPayload.pdf_url.trim().length > 0) {
                        item.pdf_url = eventPayload.pdf_url.trim();
                    }

                    const slideNumber = eventPayload.slide_number;
                    if (typeof slideNumber === 'number' && Number.isFinite(slideNumber) && slideNumber > 0) {
                        const previousSlide = existing.slidesMap.get(slideNumber) || { slide_number: slideNumber };
                        existing.slidesMap.set(slideNumber, {
                            ...previousSlide,
                            slide_number: slideNumber,
                            title: eventPayload.title ?? previousSlide.title,
                            image_url: eventPayload.image_url ?? previousSlide.image_url,
                            prompt_text: eventPayload.prompt_text ?? previousSlide.prompt_text,
                            structured_prompt: eventPayload.structured_prompt ?? previousSlide.structured_prompt,
                            rationale: eventPayload.rationale ?? previousSlide.rationale,
                            layout_type: eventPayload.layout_type ?? previousSlide.layout_type,
                            selected_inputs: eventPayload.selected_inputs ?? previousSlide.selected_inputs,
                            status: eventPayload.status ?? previousSlide.status,
                        });
                    }

                    item.slides = Array.from(existing.slidesMap.values()).sort(
                        (a: any, b: any) => (a.slide_number || 0) - (b.slide_number || 0)
                    );
                    const allReady =
                        Array.isArray(item.slides) &&
                        item.slides.length > 0 &&
                        item.slides.every((slide: any) => Boolean(slide?.image_url));
                    if (type === 'data-visual-pdf') {
                        item.status = 'completed';
                    } else if (typeof eventPayload.status === 'string' && eventPayload.status.trim().length > 0) {
                        item.status = eventPayload.status;
                    } else {
                        item.status = allReady ? 'completed' : (item.status || 'streaming');
                    }
                    return;
                }

                const slidesMap = new Map<number, any>();
                const firstSlideNumber = eventPayload.slide_number;
                if (typeof firstSlideNumber === 'number' && Number.isFinite(firstSlideNumber) && firstSlideNumber > 0) {
                    slidesMap.set(firstSlideNumber, {
                        slide_number: firstSlideNumber,
                        title: eventPayload.title,
                        image_url: eventPayload.image_url,
                        prompt_text: eventPayload.prompt_text,
                        structured_prompt: eventPayload.structured_prompt,
                        rationale: eventPayload.rationale,
                        layout_type: eventPayload.layout_type,
                        selected_inputs: eventPayload.selected_inputs,
                        status: eventPayload.status,
                    });
                }

                const nextItem: any = {
                    id: `visual-${baseArtifactId}`,
                    type: 'artifact',
                    timestamp,
                    artifactId: baseArtifactId,
                    title:
                        (typeof eventPayload.deck_title === 'string' && eventPayload.deck_title.trim().length > 0)
                            ? eventPayload.deck_title.trim()
                            : (typeof eventPayload.title === 'string' && eventPayload.title.trim().length > 0)
                                ? eventPayload.title.trim()
                                : 'Generated Slides',
                    icon: 'Image',
                    kind: deckKind,
                    mode: inferredMode || undefined,
                    pdf_url:
                        typeof eventPayload.pdf_url === 'string' && eventPayload.pdf_url.trim().length > 0
                            ? eventPayload.pdf_url.trim()
                            : undefined,
                    aspectRatio: readAspectRatio(eventPayload),
                    slides: Array.from(slidesMap.values()).sort(
                        (a: any, b: any) => (a.slide_number || 0) - (b.slide_number || 0)
                    ),
                    status:
                        type === 'data-visual-pdf'
                            ? 'completed'
                            : (typeof eventPayload.status === 'string' && eventPayload.status.trim().length > 0)
                                ? eventPayload.status
                                : 'streaming',
                };

                visualDeckMap.set(baseArtifactId, {
                    item: nextItem as TimelineEvent,
                    lastTimestamp: timestamp,
                    slidesMap,
                });
                return;
            }

            if (type === 'data-coordinator-followups') {
                const options = Array.isArray(eventPayload.options)
                    ? eventPayload.options
                        .map((option: any, index: number) => ({
                            id: typeof option?.id === 'string' && option.id.trim().length > 0
                                ? option.id.trim()
                                : `${idSeed}-followup-${index + 1}`,
                            prompt: typeof option?.prompt === 'string' ? option.prompt.trim() : '',
                        }))
                        .filter((option: any) => option.prompt.length > 0)
                        .slice(0, 3)
                    : [];

                if (options.length === 0) return;

                items.push({
                    id: `${idSeed}-coordinator-followups`,
                    type: 'coordinator_followups',
                    timestamp,
                    question: typeof eventPayload.question === 'string' ? eventPayload.question : undefined,
                    options,
                } as any);
                return;
            }

            if (type === 'data-writer-output') {
                const artifactType = typeof eventPayload.artifact_type === 'string' ? eventPayload.artifact_type : 'report';
                if (artifactType === 'outline') return;

                const baseArtifactId = eventPayload.artifact_id || `${idSeed}-writer`;
                const artifactId =
                    artifactType === 'writer_character_sheet'
                        ? CHARACTER_SHEET_BUNDLE_ARTIFACT_ID
                        : baseArtifactId;
                const existing = writerArtifactMap.get(artifactId);
                if (existing) {
                    existing.lastTimestamp = timestamp;
                    existing.item = {
                        ...(existing.item as any),
                        timestamp,
                        artifactId,
                        title: eventPayload.title || 'Writer Output',
                        icon: 'BookOpen',
                        kind: artifactType,
                        status: typeof eventPayload.status === 'string' ? eventPayload.status : undefined,
                    } as any;
                    return;
                }

                writerArtifactMap.set(artifactId, {
                    item: {
                        id: `writer-${artifactId}`,
                        type: 'artifact',
                        timestamp,
                        artifactId,
                        title: eventPayload.title || 'Writer Output',
                        icon: 'BookOpen',
                        kind: artifactType,
                        status: typeof eventPayload.status === 'string' ? eventPayload.status : undefined,
                    } as any,
                    lastTimestamp: timestamp,
                });
                return;
            }
        };

        const hasDataPartsInMessages = messages.some((msg) =>
            Array.isArray(msg.parts) &&
            msg.parts.some((part: any) => typeof part?.type === 'string' && part.type.startsWith('data-'))
        );

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
                const userFileParts: Array<{ type: 'file'; url: string; mediaType?: string; filename?: string }> = [];

                const flushText = (indexFallback: number) => {
                    const hasFileParts = msg.role === 'user' && userFileParts.length > 0;
                    if (!textBuffer.trim() && !hasFileParts) {
                        textBuffer = '';
                        textStartIndex = -1;
                        return;
                    }

                    const logicalIndex = textStartIndex >= 0 ? textStartIndex : indexFallback
                    const timestamp = baseTimestamp + logicalIndex;
                    const parts: any[] = [];
                    if (textBuffer) {
                        parts.push({ type: 'text', text: textBuffer });
                    }
                    if (hasFileParts) {
                        parts.push(...userFileParts);
                        userFileParts.length = 0;
                    }

                    items.push({
                        id: `${messageId}-text-${logicalIndex}`,
                        type: 'message',
                        timestamp,
                        message: {
                            id: msg.id,
                            role: msg.role,
                            content: textBuffer,
                            parts,
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

                    if (
                        p.type === 'file' &&
                        msg.role === 'user' &&
                        typeof p.url === 'string' &&
                        p.url.length > 0
                    ) {
                        userFileParts.push({
                            type: 'file',
                            url: p.url,
                            mediaType: typeof p.mediaType === 'string' ? p.mediaType : undefined,
                            filename: typeof p.filename === 'string' ? p.filename : undefined,
                        });
                        return;
                    }

                    flushText(partIndex);
                    flushReasoning(partIndex);

                    if (typeof p.type === 'string' && p.type.startsWith('data-')) {
                        ingestStructuredEvent(
                            p.type,
                            p.data,
                            baseTimestamp + partIndex,
                            partId
                        );
                    }
                });

                flushText(msg.parts.length);
                flushReasoning(msg.parts.length);
            }

            // Fallback: if we have parts but added nothing, OR if we have no parts
            const itemsAddedForMessage = items.length - beforeLength;
            if (itemsAddedForMessage === 0) {
                const content = (msg as any).content || '';
                const fileParts = Array.isArray(msg.parts)
                    ? msg.parts.filter((part: any) => part?.type === 'file')
                    : [];
                // Add message if there's content or if it's a user message (user messages should always be visible)
                if (content || msg.role === 'user' || fileParts.length > 0) {
                    items.push({
                        id: messageId,
                        type: 'message',
                        timestamp: baseTimestamp,
                        message: {
                            id: msg.id,
                            role: msg.role,
                            content: content,
                            parts: fileParts.length > 0 ? fileParts : undefined,
                            toolInvocations: (msg as any).toolInvocations,
                        } as any
                    });
                }
            }
        });

        // Fallback for snapshots or environments where data-* parts are not attached to messages.
        if (!hasDataPartsInMessages && data && data.length > 0) {
            data.forEach((event, idx) => {
                if (!event || typeof event !== 'object') return;
                const type = event.type as string;
                if (!type.startsWith('data-')) return;
                ingestStructuredEvent(
                    type,
                    (event as any).data || {},
                    getDataEventTimestamp(event, idx),
                    `stream-${idx}`
                );
            });
        }

        analystMap.forEach(({ item, lastTimestamp }) => {
            item.timestamp = lastTimestamp;
            items.push(item);
        });
        outlineMap.forEach(({ item, lastTimestamp }) => {
            item.timestamp = lastTimestamp;
            items.push(item);
        });
        writerArtifactMap.forEach(({ item, lastTimestamp }) => {
            item.timestamp = lastTimestamp;
            items.push(item);
        });
        visualDeckMap.forEach(({ item, lastTimestamp }) => {
            item.timestamp = lastTimestamp;
            items.push(item);
        });

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
        const readAspectRatio = (payload: any): string | null => {
            if (!payload || typeof payload !== 'object') return null;
            if (typeof payload.aspect_ratio === 'string' && payload.aspect_ratio.trim().length > 0) {
                return payload.aspect_ratio.trim();
            }
            if (
                payload.metadata &&
                typeof payload.metadata === 'object' &&
                typeof payload.metadata.aspect_ratio === 'string' &&
                payload.metadata.aspect_ratio.trim().length > 0
            ) {
                return payload.metadata.aspect_ratio.trim();
            }
            return null;
        };

        for (const event of data) {
            if (!event || typeof event !== 'object') continue;
            const type = event.type as string;
            if (!type || !type.startsWith('data-visual-')) continue;

            const payload = event.data || {};
            const inferredMode = inferVisualizerModeFromPayload(payload, deck?.mode || null);
            const artifactId = payload.artifact_id || deck?.artifactId || 'visual_deck';
            const payloadAspectRatio = readAspectRatio(payload);

            if (!deck || deck.artifactId !== artifactId) {
                deck = {
                    artifactId,
                    title: payload.deck_title || payload.title || deck?.title || 'Generated Slides',
                    slides: [],
                    status: 'streaming',
                    pdf_url: payload.pdf_url,
                    mode: inferredMode,
                    aspectRatio: payloadAspectRatio || undefined,
                };
            } else if (inferredMode) {
                deck.mode = inferredMode;
            }

            if (payloadAspectRatio) {
                deck.aspectRatio = payloadAspectRatio;
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
