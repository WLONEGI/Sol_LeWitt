import { test, expect } from '@playwright/test';

test('renders execution plan from data stream', async ({ page }) => {
    // Mock the chat API to return a stream with a plan update
    await page.route('/api/chat', async route => {
        const planData = {
            type: 'data-plan_update',
            data: {
                title: "Mock Execution Plan",
                description: "Testing plan rendering",
                plan: [
                    {
                        id: 1,
                        capability: "researcher",
                        title: "Research Topic",
                        instruction: "Find info",
                        description: "Gathering data",
                        status: "completed",
                        result_summary: "Found results"
                    },
                    {
                        id: 2,
                        capability: "writer",
                        title: "Draft Story",
                        instruction: "Write content",
                        description: "Writing slides",
                        status: "in_progress"
                    }
                ]
            }
        };

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
    const input = page.getByRole('textbox').first();
    await input.fill('Generate plan');
    await input.press('Enter');

    // Verify the plan overlay appears (current step summary)
    await expect(page.getByText('Draft Story').first()).toBeVisible();
    await expect(page.getByText(/2\s*\/\s*2/)).toBeVisible();

    // Expand to see full plan details
    await page.getByRole('button', { name: 'Expand plan' }).click();
    await expect(page.getByText('Draft Story').first()).toBeVisible();
});
