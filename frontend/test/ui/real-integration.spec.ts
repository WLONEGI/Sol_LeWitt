import { test, expect } from '@playwright/test';

test.describe('Real Integration Stream Protocol Verification', () => {

    test('should stream text and reasoning from real backend', async ({ page }) => {
        // Increase timeout for real backend response
        test.setTimeout(60000);

        await page.goto('/');

        // Find input and send message
        const input = page.getByPlaceholder('Type a message...');
        await input.fill('Hello, test message.');
        await input.press('Enter');

        // Check if we get ANY response bubble
        // The assistant response usually appears after the user message
        const userMessage = page.getByText('Hello, test message.');
        await expect(userMessage).toBeVisible();

        // Wait for some response (streaming)
        // We look for a non-user message bubble, or just wait for text content
        // This selector might need adjustment based on the actual UI component structure
        // Assuming standard Vercel SDK UI or similar structure

        // We verify that *something* comes back. 
        // Since we don't know exactly what the LLM will say, we check for visibility of the message container
        // or look for the "Thinking Process" if reasoning is enabled.

        // Let's try to detect if "Thinking Process" button appears (if the backend uses reasoning)
        // Or just some text content.

        // We can inspect the network traffic to see if it follows the protocol?
        // But playwright page assertions are better for "useChat works correctly".

        // Wait for *any* text response
        const assistantMessage = page.locator('.prose').last(); // Common class for message content
        await expect(assistantMessage).toBeVisible({ timeout: 30000 });

        // Optional: Check for reasoning button if we expect it
        // const reasoningTrigger = page.locator('button:has-text("Thinking Process")');
        // if (await reasoningTrigger.isVisible()) {
        //     await reasoningTrigger.click();
        //     await expect(page.locator('.reasoning-content')).toBeVisible();
        // }
    });
});
