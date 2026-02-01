/**
 * Attempts to parse incomplete JSON by auto-closing brackets.
 * Useful for streaming partial JSON from LLM tool calls.
 */
export function parsePartialJSON<T = any>(input: string): {
    parsed: T | null;
    isComplete: boolean;
} {
    if (!input || typeof input !== 'string') {
        return { parsed: null, isComplete: false };
    }

    // Attempt 1: Parse as-is (complete JSON)
    try {
        return { parsed: JSON.parse(input), isComplete: true };
    } catch {
        // Continue to repair attempt
    }

    // Attempt 2: Auto-close brackets using stack-based approach
    let repaired = input.trimEnd();

    // Remove trailing comma that would cause parse error
    repaired = repaired.replace(/,\s*$/, '');

    // Build a stack of unclosed brackets in order
    const stack: string[] = [];
    let inString = false;
    let escapeNext = false;

    for (const char of repaired) {
        if (escapeNext) {
            escapeNext = false;
            continue;
        }
        if (char === '\\' && inString) {
            escapeNext = true;
            continue;
        }
        if (char === '"') {
            inString = !inString;
            continue;
        }
        if (inString) continue;

        if (char === '{') stack.push('}');
        else if (char === '[') stack.push(']');
        else if (char === '}' || char === ']') {
            if (stack.length > 0 && stack[stack.length - 1] === char) {
                stack.pop();
            }
        }
    }

    // Close brackets in reverse order (LIFO)
    while (stack.length > 0) {
        repaired += stack.pop();
    }

    try {
        return { parsed: JSON.parse(repaired), isComplete: false };
    } catch {
        return { parsed: null, isComplete: false };
    }
}

/**
 * Extracts a partial array from incomplete JSON.
 * Particularly useful for streaming arrays of objects.
 */
export function parsePartialArray<T = any>(input: string): T[] {
    const { parsed } = parsePartialJSON<T[]>(input);
    return Array.isArray(parsed) ? parsed : [];
}
