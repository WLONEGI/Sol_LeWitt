"use client"

import { useMemo } from 'react'
import type { UIMessage } from 'ai'
import { TimelineEvent, MessageTimelineItem, ResearchReportTimelineItem } from "../types/timeline"

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
    // Extract the latest plan from data stream
    const latestPlan = useMemo(() => {
        if (!data || data.length === 0) return null;

        // Find the latest data-plan
        for (let i = data.length - 1; i >= 0; i--) {
            const event = data[i];
            if (event && typeof event === 'object' && event.type === 'data-plan') {
                return event.data;
            }
        }
        return null;
    }, [data])

    // Convert messages to timeline items
    const timeline = useMemo<TimelineEvent[]>(() => {
        const items: TimelineEvent[] = [];

        messages.forEach((msg, msgIndex) => {
            const messageId = `msg-${msg.id}`;
            const baseTimestamp = Date.now() - (messages.length - msgIndex) * 1000;

            // Process parts and interleave them
            if (msg.parts && msg.parts.length > 0) {
                msg.parts.forEach((part, partIndex) => {
                    const partId = `${messageId}-part-${partIndex}`;
                    const p = part as any;

                    if (p.type === 'text') {
                        // For text parts, we either push a new item or append to the last message item if it exists
                        // To keep it simple and match the "per-part" interleaving, we create items for each
                        items.push({
                            id: partId,
                            type: 'message',
                            timestamp: baseTimestamp + partIndex,
                            message: {
                                id: msg.id,
                                role: msg.role,
                                content: p.text,
                                parts: [part],
                                toolInvocations: (msg as any).toolInvocations,
                            } as any
                        });
                    } else if (p.type === 'reasoning') {
                        items.push({
                            id: partId,
                            type: 'message',
                            timestamp: baseTimestamp + partIndex,
                            message: {
                                id: msg.id,
                                role: msg.role,
                                content: '',
                                reasoning: p.text,
                                parts: [part],
                            } as any
                        });
                    } else if (typeof p.type === 'string' && p.type.startsWith('data-')) {
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
                                // Find the corresponding start item and update it, 
                                // or add a completion event if we want distinct items
                                // For the pill UI in timeline, updating the status is usually better
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
            } else {
                // Fallback for messages without parts (legacy or pure content)
                items.push({
                    id: messageId,
                    type: 'message',
                    timestamp: baseTimestamp,
                    message: {
                        id: msg.id,
                        role: msg.role,
                        content: (msg as any).content || '',
                        toolInvocations: (msg as any).toolInvocations,
                    } as any
                });
            }
        });

        // Add any remaining research events from the global data stream that might not be in parts
        // (This is a safety net for other custom events like data-plan or data-outline)
        return items.sort((a, b) => a.timestamp - b.timestamp);
    }, [messages])

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

    return { timeline, latestPlan, latestOutline }
}
