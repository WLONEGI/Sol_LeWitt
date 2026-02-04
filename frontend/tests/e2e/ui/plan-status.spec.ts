import { test, expect } from '@playwright/test';

test('renders execution plan from data stream', async ({ page }) => {
    // Mock the chat API to return a stream with a plan update
    await page.route('/api/chat', async route => {
        const planData = {
            type: 'plan_update',
            data: {
                title: "Mock Execution Plan",
                description: "Testing plan rendering",
                plan: [
                    {
                        id: 1,
                        role: "researcher",
                        title: "Research Topic",
                        instruction: "Find info",
                        description: "Gathering data",
                        status: "completed",
                        result_summary: "Found results"
                    },
                    {
                        id: 2,
                        role: "storywriter",
                        title: "Draft Story",
                        instruction: "Write content",
                        description: "Writing slides",
                        status: "in_progress"
                    }
                ]
            }
        };

        // Construct SSE stream
        // Sending ONLY the data part to avoid potentially confusing text part validation errors.
        // Format: data: <JSON-object>\n\n
        const responseBody = `data: ${JSON.stringify(planData)}\n\n`;

        await route.fulfill({
            status: 200,
            contentType: 'text/event-stream',
            body: responseBody
        });
    });

    // Debug console
    page.on('console', msg => console.log(`BROWSER LOG: ${msg.text()}`));

    await page.goto('/');

    // Send a message to trigger the flow
    const input = page.getByPlaceholder('Type a message...');
    await input.fill('Generate plan');
    await input.press('Enter');

    // Verify the plan overlay appears (collapsed header)
    await expect(page.getByText('Step 2: Draft Story')).toBeVisible();

    // Expand to see full plan details
    await page.getByRole('button', { name: 'Expand plan' }).click();
    await expect(page.getByText('Research Topic')).toBeVisible();
    await expect(page.getByText('Draft Story', { exact: true })).toBeVisible();
    await expect(page.getByText('Gathering data')).toBeVisible();
});
