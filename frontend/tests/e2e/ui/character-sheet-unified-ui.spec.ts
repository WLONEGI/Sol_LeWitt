import { expect, test, type Route } from '@playwright/test';

async function mockCharacterSheetStream(page: any) {
  await page.route('/api/chat', async (route: Route) => {
    const sse = [
      {
        type: 'data-writer-output',
        data: {
          artifact_id: 'step_11_story',
          artifact_type: 'writer_character_sheet',
          title: 'Character Sheet',
          status: 'completed',
          output: {
            execution_summary: 'character sheet completed',
            characters: [
              {
                character_id: 'char_001',
                name: 'Aoi',
                story_role: 'Protagonist',
                speech_style: 'calm',
              },
            ],
          },
        },
      },
      {
        type: 'data-visual-image',
        data: {
          artifact_id: 'step_12_visual',
          mode: 'character_sheet_render',
          slide_number: 1,
          title: 'Character Sheet: Aoi',
          image_url: 'https://example.com/char-aoi.png',
          prompt_text: '#Character1\\nMode: character_sheet_render',
          status: 'completed',
        },
      },
      {
        type: 'data-visual-pdf',
        data: {
          artifact_id: 'step_12_visual',
          mode: 'character_sheet_render',
          status: 'completed',
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
}

async function sendPrompt(page: any) {
  await page.goto('/');

  const input = page.getByRole('textbox').first();
  await input.fill('キャラクターシートを作成して');
  await input.press('Enter');
}

test('opens unified character sheet UI from writer summary card', async ({ page }) => {
  await mockCharacterSheetStream(page);
  await sendPrompt(page);

  await expect(page.getByText('Characters: 1')).toBeVisible();
  await expect(page.getByText('Aoi').first()).toBeVisible();
  await expect(page.getByRole('button', { name: 'Open Character Sheet' })).toBeVisible();
  await expect(page.getByAltText('Slide 1')).toBeVisible();

  await page.getByRole('button', { name: 'Open Character Sheet' }).click();
  await expect(page.getByRole('button', { name: 'Settings' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Sheets' })).toBeVisible();
  await page.getByRole('button', { name: 'Sheets' }).click();
  await expect(page.getByRole('img', { name: 'Character Sheet: Aoi' })).toBeVisible();
});

test('opens unified character sheet UI from visualizer slide card', async ({ page }) => {
  await mockCharacterSheetStream(page);
  await sendPrompt(page);

  await page.getByAltText('Slide 1').first().click({ force: true });
  await expect(page.getByRole('button', { name: 'Settings' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Sheets' })).toBeVisible();
  await page.getByRole('button', { name: 'Sheets' }).click();
  await expect(page.getByRole('img', { name: 'Character Sheet: Aoi' })).toBeVisible();
});
