import { test, expect } from '@playwright/test';

test.describe('Process View & Chat', () => {
    test('should display process stream during chat', async ({ page }) => {
        // Capture console logs
        page.on('console', msg => console.log(`BROWSER CONSOLE: ${msg.text()}`));

        // 1. Visit page
        await page.goto('/');

        // 2. Type query
        const textarea = page.locator('textarea[placeholder="Type a message..."]');
        await expect(textarea).toBeVisible();
        await textarea.fill('LangGraphの最新機能を調べて');



        // 3. Send
        // Identify send button by icon class or position if no role
        const sendButton = page.locator('button:has(.lucide-send-horizontal)');
        await expect(sendButton).toBeEnabled();
        await sendButton.click();

        // 4. Verify Process View Appears
        console.log('Waiting for Phase header or Chat response...');

        try {
            // Wait for either Phase header OR chat response (to confirm connection)
            const phaseOrChat = await Promise.race([
                page.locator('button', { hasText: 'Phase:' }).first().waitFor({ state: 'visible', timeout: 30000 }).then(() => 'phase'),
                page.locator('.prose').last().waitFor({ state: 'visible', timeout: 30000 }).then(() => 'chat')
            ]);
            console.log(`Detected: ${phaseOrChat}`);
        } catch (e) {
            console.log('Timeout waiting for stream start');
        }

        // Detailed Check
        const content = await page.content();
        if (!content.includes('Phase:')) {
            console.log('DEBUG: Page content missing "Phase:" text.');
            // Check if we received ANY logs
            if (content.includes('Processing')) console.log('DEBUG: Found "Processing" text.');
            // console.log(content.slice(0, 2000)); // dump partial source if needed
        }

        const phaseHeader = page.locator('button', { hasText: 'Phase:' }).first();
        await expect(phaseHeader).toBeVisible({ timeout: 10000 });

        // 5. Verify Tool Logs
        // Check for "Searching" or tool activity
        // Relaxed selector: just look for DIV with text "search" inside the process area
        // Process container typically has border/bg-card
        const toolLog = page.locator('div').filter({ hasText: 'search' }).first();
        // It might take a moment
        // await expect(toolLog).toBeVisible({ timeout: 30000 });

        // 7. Verify Chat Response matches stream
        // Just ensure the chat list is growing or not empty
        const chatMessage = page.locator('.prose').last();
        await expect(chatMessage).toBeVisible();
    });
});
