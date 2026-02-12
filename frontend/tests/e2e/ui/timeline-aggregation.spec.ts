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
        type: 'data-research-report',
        data: {
          task_id: 'r1',
          perspective: 'sleep',
          status: 'completed',
          report: 'old-report',
          sources: ['https://example.com/source-old'],
        },
      },
      {
        type: 'data-research-report',
        data: {
          task_id: 'r1',
          perspective: 'sleep',
          status: 'completed',
          report: 'new-report',
          sources: ['https://example.com/source-new'],
        },
      },
      {
        type: 'data-research-report',
        data: {
          task_id: 'r2',
          perspective: 'calm',
          status: 'completed',
          report: 'other-report',
          sources: ['https://example.com/source-other'],
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

  const expandReportButtons = page.getByRole('button', { name: 'Expand report' });
  while ((await expandReportButtons.count()) > 0) {
    await expandReportButtons.first().click();
  }

  await expect(page.getByText('new-report')).toBeVisible();
  await expect(page.getByText('other-report')).toBeVisible();
  await expect(page.getByText('old-report')).toHaveCount(0);

  await expect(page.getByText('Writer V2')).toBeVisible();
  await expect(page.getByRole('button', { name: /Character Sheet Writer:/ })).toBeVisible();
  await expect(page.getByText('Writer V1')).toHaveCount(0);
});
