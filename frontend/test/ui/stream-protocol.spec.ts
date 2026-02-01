import { test, expect } from '@playwright/test';

/**
 * UI Message Stream Protocol Verification Tests (Data Stream Protocol v2)
 */

test.describe('Data Stream Protocol Verification', () => {

    test('should stream text and reasoning correctly', async ({ page }) => {
        page.on('console', msg => console.log(`BROWSER [${msg.type()}]: ${msg.text()}`));
        // Intercept API call and mock SSE stream (v2)
        await page.route('**/api/chat', async (route) => {
            const encoder = new TextEncoder();

            const streamParts = [
                'r:"Thinking about the design..."\n',
                '0:"The design is ready."\n',
                'd:{"finishReason":"stop"}\n'
            ];

            await route.fulfill({
                status: 200,
                contentType: 'text/plain; charset=utf-8',
                body: new ReadableStream({
                    start(controller) {
                        for (const part of streamParts) {
                            controller.enqueue(encoder.encode(part));
                        }
                        controller.close();
                    }
                }) as any
            });
        });

        await page.goto('/');

        // Find input and send message
        const input = page.getByPlaceholder('Type a message...');
        await input.fill('Verify stream protocol');
        await input.press('Enter');

        // Verify Reasoning
        const reasoningTrigger = page.locator('button:has-text("Thinking Process")');
        await expect(reasoningTrigger).toBeVisible({ timeout: 15000 });
        await reasoningTrigger.click();

        await expect(page.getByText('Thinking about the design...')).toBeVisible();

        // Verify Text Content
        await expect(page.getByText('The design is ready.')).toBeVisible();
    });

    test('should handle custom data-ui_step_update events', async ({ page }) => {
        page.on('console', msg => console.log(`BROWSER [${msg.type()}]: ${msg.text()}`));
        await page.route('**/api/chat', async (route) => {
            const encoder = new TextEncoder();

            const streamParts = [
                '2:[{"type":"ui_step_update","status":"active","label":"planner","id":"step-1"}]\n',
                '0:"I am planning."\n',
                'd:{"finishReason":"stop"}\n'
            ];

            await route.fulfill({
                status: 200,
                contentType: 'text/plain; charset=utf-8',
                body: new ReadableStream({
                    start(controller) {
                        for (const part of streamParts) {
                            controller.enqueue(encoder.encode(part));
                        }
                        controller.close();
                    }
                }) as any
            });
        });

        await page.goto('/');
        await page.getByPlaceholder('Type a message...').fill('Test agent status');
        await page.getByPlaceholder('Type a message...').press('Enter');

        // Check if AgentStatusIndicator reflects the status
        const indicator = page.getByTestId('agent-status-indicator');
        await expect(indicator).toBeVisible({ timeout: 10000 });
        await expect(indicator).toContainText('planner');
    });

    test('should display error messages from the stream', async ({ page }) => {
        page.on('console', msg => console.log(`BROWSER [${msg.type()}]: ${msg.text()}`));
        await page.route('**/api/chat', async (route) => {
            const encoder = new TextEncoder();

            const streamParts = [
                'e:{"message":"Simulated stream error"}\n',
            ];

            await route.fulfill({
                status: 200,
                contentType: 'text/plain; charset=utf-8',
                body: new ReadableStream({
                    start(controller) {
                        for (const part of streamParts) {
                            controller.enqueue(encoder.encode(part));
                        }
                        controller.close();
                    }
                }) as any
            });
        });

        await page.goto('/');
        await page.getByPlaceholder('Type a message...').fill('Trigger error');
        await page.getByPlaceholder('Type a message...').press('Enter');

        // Check for error display
        await expect(page.getByText('Simulated stream error')).toBeVisible({ timeout: 10000 });
    });
});
