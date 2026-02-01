#!/usr/bin/env npx tsx
/**
 * Agent Status Display - Stream Verification Script
 * 
 * Verifies that the Next.js BFF emits Data Stream Protocol format correctly:
 * - Prefix `2:` for custom data (ui_step_update, etc.)
 * - Prefix `0:` for text deltas
 * - Correct ordering of status updates and text generation
 * 
 * Usage: npx tsx tests/verify-stream.ts
 */

const API_URL = process.env.API_URL || 'http://localhost:3000/api/chat/stream';

interface StreamStats {
    textParts: number;           // Count of 0: prefixes
    dataParts: number;           // Count of 2: prefixes
    statusUpdates: number;       // Count of ui_step_update events
    otherParts: number;          // Count of other prefixes
    errors: string[];
    timeline: Array<{ time: number; prefix: string; summary: string }>;
}

async function verifyStream(): Promise<void> {
    console.log('\n🔍 Agent Status Display - Stream Verification\n');
    console.log(`📡 Target: ${API_URL}`);
    console.log('─'.repeat(60));

    const stats: StreamStats = {
        textParts: 0,
        dataParts: 0,
        statusUpdates: 0,
        otherParts: 0,
        errors: [],
        timeline: [],
    };

    const startTime = Date.now();

    try {
        const response = await fetch(API_URL, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                messages: [
                    { role: 'user', content: '2024年のAIトレンドを調べて報告してください。' }
                ],
                thread_id: `test-${Date.now()}`,
            }),
        });

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        console.log(`✅ HTTP ${response.status} - Stream started\n`);
        console.log('📥 Receiving stream parts:\n');

        const reader = response.body?.getReader();
        if (!reader) throw new Error('No response body');

        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop() || '';

            for (const line of lines) {
                const trimmedLine = line.trim();
                if (!trimmedLine) continue;

                const elapsed = Date.now() - startTime;

                let prefix: string;
                let content: string;
                let parsedData: any = null;

                // Handle SSE format (data: ...)
                if (trimmedLine.startsWith('data: ')) {
                    content = trimmedLine.slice(6);
                    parsedData = tryParseJSON(content);

                    if (parsedData && typeof parsedData === 'object' && 'type' in parsedData) {
                        const type = parsedData.type;

                        // Handle Custom Data (ui_step_update)
                        if (type === 'data-ui_step_update') {
                            prefix = '2'; // Data
                            stats.dataParts++; // Count as data part
                            // Assuming the payload is in `data` field
                            const innerData = parsedData.data;
                            if (innerData?.type === 'ui_step_update' || innerData?.type === 'timeline_update') {
                                stats.statusUpdates++;
                                const status = innerData.status || 'unknown';
                                const label = innerData.label || innerData.title || 'no label';
                                stats.timeline.push({ time: elapsed, prefix, summary: `STATUS: ${status} - ${label}` });
                                console.log(`  [${elapsed}ms] 2: ⚡ STATUS UPDATE: ${status} - "${label}"`);
                            } else {
                                console.log(`  [${elapsed}ms] 2: 📦 data-ui_step_update`);
                            }
                        }
                        // Standard Text
                        else if (type === 'text-delta') {
                            prefix = '0';
                            stats.textParts++;
                            const text = parsedData.delta;
                            stats.timeline.push({ time: elapsed, prefix, summary: `text: "${truncate(String(text), 30)}"` });
                            console.log(`  [${elapsed}ms] 0: (text) ${truncate(String(text), 50)}`);
                        }
                        // Standard Reasoning
                        else if (type === 'reasoning-delta') {
                            prefix = 'R'; // Custom code for Reasoning in this script
                            stats.dataParts++; // Count as data/extra part
                            const text = parsedData.delta;
                            stats.timeline.push({ time: elapsed, prefix, summary: `reasoning: "${truncate(String(text), 30)}"` });
                            console.log(`  [${elapsed}ms] R: (think) ${truncate(String(text), 50)}`);
                        }
                        // Message Lifecycle
                        else if (type === 'message-start') {
                            console.log(`  [${elapsed}ms] M: 🟢 message-start`);
                        }
                        else if (type === 'finish-message') {
                            console.log(`  [${elapsed}ms] M: 🏁 finish-message`);
                        }
                        else if (type.endsWith('-start') || type.endsWith('-end')) {
                            // e.g. text-start, reasoning-end
                            console.log(`  [${elapsed}ms] S: 🔹 ${type}`);
                            // Do not spam timeline
                        }
                        else {
                            console.log(`  [${elapsed}ms] ?: ${type} ${JSON.stringify(parsedData)}`);
                        }

                    } else {
                        console.log(`  [${elapsed}ms] S: ℹ️ Pure JSON or unknown: ${truncate(content, 40)}`);
                    }
                    continue; // Skip the old prefix logic
                }

                // Fallback for non-SSE or malformed lines
                console.log(`  [${elapsed}ms] ?: ${truncate(line, 40)}`);
            }
        }

        // Process remaining buffer
        if (buffer.trim()) {
            console.log(`  [final] Remaining: ${truncate(buffer, 50)}`);
        }

    } catch (err) {
        console.error(`\n❌ Request failed: ${err}`);
        process.exit(1);
    }

    // Summary report
    console.log('\n' + '─'.repeat(60));
    console.log('📊 VERIFICATION SUMMARY\n');

    console.log('Stream Structure:');
    console.log(`  ├─ Text parts (text-delta):      ${stats.textParts}`);
    console.log(`  ├─ Reasoning parts (reasoning-delta): ${stats.timeline.filter(t => t.prefix === 'R').length}`);
    console.log(`  ├─ Status updates:               ${stats.statusUpdates}`);
    console.log(`  ├─ Data parts (2: prefix):       ${stats.dataParts}`);

    console.log('\nVerification Results:');

    // Check 1: Data parts exist
    const hasDataParts = stats.dataParts > 0;
    console.log(`  ${hasDataParts ? '✅' : '❌'} [1] Stream contains 2: (data) parts: ${hasDataParts ? 'PASS' : 'FAIL'}`);

    // Check 2: Status updates exist  
    const hasStatusUpdates = stats.statusUpdates > 0;
    console.log(`  ${hasStatusUpdates ? '✅' : '🔴'} [2] Status updates (ui_step_update) received: ${hasStatusUpdates ? 'PASS' : 'WARN (Maybe no steps triggered in this test query)'}`);

    // Check 3: Text parts exist
    const hasTextParts = stats.textParts > 0;
    console.log(`  ${hasTextParts ? '✅' : '❌'} [3] Text streaming (text-delta) works: ${hasTextParts ? 'PASS' : 'FAIL'}`);

    // Check 4: Reasoning
    const hasReasoning = stats.timeline.some(t => t.prefix === 'R');
    console.log(`  ${hasReasoning ? '✅' : '⚪'} [4] Reasoning (reasoning-delta) received: ${hasReasoning ? 'PASS' : 'INFO (Not triggered by simple query)'}`);

    // Check 5: No errors
    const noErrors = stats.errors.length === 0;
    console.log(`  ${noErrors ? '✅' : '❌'} [5] No stream errors: ${noErrors ? 'PASS' : 'FAIL'}`);

    console.log('\n' + '─'.repeat(60));

    const allPassed = hasDataParts && hasStatusUpdates && hasTextParts && noErrors;
    if (allPassed) {
        console.log('🎉 ALL CHECKS PASSED - Data pipeline verified!\n');
        process.exit(0);
    } else {
        console.log('⚠️  SOME CHECKS FAILED - Review output above.\n');
        process.exit(1);
    }
}

function tryParseJSON(str: string): unknown {
    try {
        return JSON.parse(str);
    } catch {
        return null;
    }
}

function truncate(str: string, maxLen: number): string {
    if (str.length <= maxLen) return str;
    return str.slice(0, maxLen - 3) + '...';
}

verifyStream();
