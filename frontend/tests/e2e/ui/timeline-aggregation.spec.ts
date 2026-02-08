import { expect, test } from '@playwright/test';

test('aggregates timeline cards by artifact and keeps latest payload', async ({ page }) => {
  await page.route('/api/chat', async (route) => {
    const sse = [
      {
        type: 'data-outline',
        data: {
          artifact_id: 'step_1_story',
          title: 'Slide Outline',
          slides: [{ slide_number: 1, title: 'old-outline', bullet_points: [] }],
        },
      },
      {
        type: 'data-outline',
        data: {
          artifact_id: 'step_1_story',
          title: 'Slide Outline',
          slides: [{ slide_number: 1, title: 'new-outline', bullet_points: [] }],
        },
      },
      {
        type: 'data-outline',
        data: {
          artifact_id: 'step_2_story',
          title: 'Slide Outline',
          slides: [{ slide_number: 1, title: 'other-outline', bullet_points: [] }],
        },
      },
      {
        type: 'data-image-search-results',
        data: {
          artifact_id: 'step_5_research_1',
          task_id: 'r1',
          query: 'old-query',
          perspective: 'sleep',
          candidates: [
            {
              image_url: 'https://example.com/old.png',
              source_url: 'https://example.com/source-old',
              license_note: 'CC BY 4.0',
              caption: 'old-candidate',
            },
          ],
        },
      },
      {
        type: 'data-image-search-results',
        data: {
          artifact_id: 'step_5_research_1',
          task_id: 'r1',
          query: 'new-query',
          perspective: 'sleep',
          candidates: [
            {
              image_url: 'https://example.com/new.png',
              source_url: 'https://example.com/source-new',
              license_note: 'CC BY-SA 4.0',
              caption: 'new-candidate',
            },
          ],
        },
      },
      {
        type: 'data-image-search-results',
        data: {
          artifact_id: 'step_5_research_2',
          task_id: 'r2',
          query: 'other-query',
          perspective: 'calm',
          candidates: [
            {
              image_url: 'https://example.com/other.png',
              source_url: 'https://example.com/source-other',
              license_note: 'CC0',
              caption: 'other-candidate',
            },
          ],
        },
      },
      {
        type: 'data-writer-output',
        data: {
          artifact_id: 'step_10_story',
          artifact_type: 'writer_story_framework',
          title: 'Writer V1',
          output: { execution_summary: 'v1' },
        },
      },
      {
        type: 'data-writer-output',
        data: {
          artifact_id: 'step_10_story',
          artifact_type: 'writer_story_framework',
          title: 'Writer V2',
          output: { execution_summary: 'v2' },
        },
      },
      {
        type: 'data-writer-output',
        data: {
          artifact_id: 'step_11_story',
          artifact_type: 'writer_character_sheet',
          title: 'Writer Character',
          output: { execution_summary: 'character' },
        },
      },
    ]
      .map((evt) => `data: ${JSON.stringify(evt)}\n\n`)
      .join('');

    await route.fulfill({
      status: 200,
      contentType: 'text/event-stream',
      body: sse,
    });
  });

  await page.goto('/');

  const input = page.getByRole('textbox').first();
  await input.fill('集約テスト');
  await input.press('Enter');

  await expect(page.getByText('new-outline')).toBeVisible();
  await expect(page.getByText('other-outline')).toBeVisible();
  await expect(page.getByText('old-outline')).toHaveCount(0);

  await expect(page.getByText('Using Tool | Image Search new-query')).toBeVisible();
  await expect(page.getByText('Using Tool | Image Search other-query')).toBeVisible();
  await expect(page.getByText('Using Tool | Image Search old-query')).toHaveCount(0);
  await expect(page.getByAltText('new-candidate')).toBeVisible();
  await expect(page.getByAltText('other-candidate')).toBeVisible();

  await expect(page.getByText('Writer V2')).toBeVisible();
  await expect(page.getByText('Writer Character')).toBeVisible();
  await expect(page.getByText('Writer V1')).toHaveCount(0);
});

