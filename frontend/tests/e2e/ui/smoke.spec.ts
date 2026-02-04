import { test, expect } from '@playwright/test';

test('chat interface smoke test', async ({ page }) => {
    await page.goto('/');

    // Verify chat input is present
    const input = page.getByPlaceholder('Type a message...');
    await expect(input).toBeVisible();

    // Try sending a message
    await input.fill('Hello from smoke test');
    await input.press('Enter');

    // Check if URL changed to a chat ID
    await expect(page).toHaveURL(/\/chat\/[0-9a-f-]{36}/);

    // Verify user message appeared in the timeline
    // In our UI, messages should appear in the main area
    await expect(page.getByText('Hello from smoke test')).toBeVisible();
});
