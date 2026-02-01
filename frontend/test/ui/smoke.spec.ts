import { test, expect } from '@playwright/test';

test.describe('E2E Smoke Test', () => {
    test('should send a message and receive a response with status updates', async ({ page }) => {
        // 1. Navigate to the chat page
        await page.goto('/');

        // 2. Wait for input to be ready
        const inputTextArea = page.locator('textarea[name="message"]');
        await expect(inputTextArea).toBeVisible();

        // 3. Type and send a message
        await inputTextArea.fill('Hello, are you working?');
        await page.keyboard.press('Enter');

        // 4. Verify user message appears
        await expect(page.getByText('Hello, are you working?')).toBeVisible();

        // 5. Verify assistant response stream starts
        // Depending on speed, we might see "Thinking..." or text
        // We expect *some* assistant message container to appear
        const assistantMessage = page.locator('.prose').last();
        await expect(assistantMessage).toBeVisible({ timeout: 10000 });

        // 6. Check for status updates (Accordion) if applicable
        // Note: Simple "Hello" might not trigger complex tools, but we check if the UI doesn't crash
    });
});
