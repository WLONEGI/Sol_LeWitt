"use client"

import { useMemo } from 'react'
import type { UIMessage } from 'ai'
import { TimelineEvent, MessageTimelineItem } from "../types/timeline"

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
    // Convert messages to timeline items
    const timeline = useMemo<TimelineEvent[]>(() => {
        const messageItems: MessageTimelineItem[] = messages.map((msg, index) => {
            return {
                id: `msg-${msg.id}`,
                type: 'message' as const,
                timestamp: Date.now() - (messages.length - index) * 1000, // Approximate ordering
                message: {
                    id: msg.id,
                    role: msg.role,
                    content: getTextFromParts(msg.parts),
                    reasoning: getReasoningFromParts(msg.parts),
                    parts: msg.parts,
                    toolInvocations: (msg as any).toolInvocations,
                } as any
            }
        })

        return messageItems
    }, [messages])

    // Extract the latest agent status from data stream
    const currentAgentStatus = useMemo(() => {
        if (!data || data.length === 0) return null;

        // Find the latest ui_step_update
        for (let i = data.length - 1; i >= 0; i--) {
            const event = data[i];
            if (event && typeof event === 'object' && event.type === 'ui_step_update') {
                return event;
            }
        }
        return null;
    }, [data])

    return { timeline, currentAgentStatus }
}
