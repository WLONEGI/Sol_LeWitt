import { expect, test } from '@playwright/test';

test('image search selection is forwarded as selected_image_inputs on next turn', async ({ page }) => {
    const selectedImage = {
        image_url: 'https://example.com/ref-1.png',
        source_url: 'https://example.com/source-1',
        license_note: 'CC BY 4.0',
        provider: 'grounded_web',
        caption: 'candidate-1',
    };

    let callCount = 0;
    let firstRequestBody: any = null;
    let secondRequestBody: any = null;

    await page.route('/api/chat', async (route) => {
        callCount += 1;
        const body = route.request().postDataJSON();

        if (callCount === 1) {
            firstRequestBody = body;
            const responseBody = `data: ${JSON.stringify({
                type: 'data-image-search-results',
                data: {
                    task_id: 'research-1',
                    query: '睡眠 リラックス イラスト',
                    perspective: 'sleep relax illustration',
                    candidates: [
                        selectedImage,
                        {
                            image_url: 'https://example.com/ref-2.png',
                            source_url: 'https://example.com/source-2',
                            license_note: 'CC BY-SA 4.0',
                            provider: 'grounded_web',
                            caption: 'candidate-2',
                        },
                    ],
                },
            })}\n\n`;

            await route.fulfill({
                status: 200,
                contentType: 'text/event-stream',
                body: responseBody,
            });
            return;
        }

        secondRequestBody = body;
        const responseBody = `data: ${JSON.stringify({
            type: 'data-plan_update',
            data: {
                title: 'Follow-up Plan',
                description: 'selected image forwarded',
                plan: [{ id: 1, capability: 'visualizer', title: 'visualize', status: 'in_progress' }],
            },
        })}\n\n`;
        await route.fulfill({
            status: 200,
            contentType: 'text/event-stream',
            body: responseBody,
        });
    });

    await page.goto('/');

    const input = page.getByRole('textbox').first();

    await input.fill('画像候補を検索して');
    await input.press('Enter');

    await expect(page.getByText(/Using Tool \| Image Search/i)).toBeVisible();
    await expect(page.getByAltText('candidate-1')).toBeVisible();

    await page.getByAltText('candidate-1').click();
    await expect(page.getByText('選択中')).toBeVisible();

    await input.fill('この画像を使って次を生成');
    await input.press('Enter');

    await expect.poll(() => callCount).toBeGreaterThan(1);
    await expect.poll(() => secondRequestBody?.selected_image_inputs?.length ?? 0).toBe(1);
    await expect(secondRequestBody.selected_image_inputs[0].image_url).toBe(selectedImage.image_url);
    await expect(secondRequestBody.selected_image_inputs[0].source_url).toBe(selectedImage.source_url);
    await expect(Array.isArray(firstRequestBody?.selected_image_inputs)).toBeTruthy();
    await expect(firstRequestBody.selected_image_inputs.length).toBe(0);
});
