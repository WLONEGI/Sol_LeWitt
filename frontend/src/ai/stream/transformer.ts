/**
 * NDJSON Stream Utilities
 * 
 * Provides utilities for parsing NDJSON (Newline Delimited JSON) streams
 * from the backend LangGraph workflow.
 */

/**
 * Parses a single line of NDJSON and returns the parsed event.
 * Returns null if the line is empty or cannot be parsed.
 */
export function parseNDJSONLine(line: string): any | null {
    const trimmed = line.trim();
    if (!trimmed) return null;

    try {
        return JSON.parse(trimmed);
    } catch (e) {
        console.warn('[StreamTransformer] Parse error:', e);
        return null;
    }
}

/**
 * Extracts custom event payload from a LangGraph event.
 * Used for on_custom_event events dispatched via adispatch_custom_event.
 */
export function extractCustomEventPayload(event: any): {
    type: string;
    data: any;
    stepId?: string;
    agentName?: string;
} | null {
    if (event?.event !== 'on_custom_event') {
        return null;
    }

    return {
        type: event.name || 'custom',
        data: event.data || {},
        stepId: event.metadata?.step_id,
        agentName: event.metadata?.agent_name
    };
}

/**
 * Creates an async generator that reads from a ReadableStream and yields parsed NDJSON events.
 * 
 * @deprecated This function consumes the stream. Use inline parsing in route handlers instead.
 * @param stream - The ReadableStream to read from
 * @param onCustomEvent - Optional callback for custom events
 */
export async function* processNDJSONStream(
    stream: ReadableStream<Uint8Array>,
    onCustomEvent?: (payload: any) => void
) {
    const reader = stream.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    try {
        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop() || '';

            for (const line of lines) {
                const event = parseNDJSONLine(line);
                if (!event) continue;

                // Handle custom events
                const customPayload = extractCustomEventPayload(event);
                if (customPayload && onCustomEvent) {
                    onCustomEvent(customPayload);
                }

                yield event;
            }
        }

        // Handle remaining buffer
        if (buffer.trim()) {
            const event = parseNDJSONLine(buffer);
            if (event) {
                const customPayload = extractCustomEventPayload(event);
                if (customPayload && onCustomEvent) {
                    onCustomEvent(customPayload);
                }
                yield event;
            }
        }

    } finally {
        reader.releaseLock();
    }
}
