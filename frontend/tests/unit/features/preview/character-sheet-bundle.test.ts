import { describe, expect, it } from 'vitest'

import {
  buildCharacterSheetBundleArtifact,
  CHARACTER_SHEET_BUNDLE_ARTIFACT_ID,
  inferVisualizerModeFromPayload,
  mergeCharacterSheetBundleWithVisual,
  mergeCharacterSheetBundleWithWriter,
  normalizeCharacterSheetBundle,
} from '@/features/preview/lib/character-sheet-bundle'

describe('character-sheet-bundle', () => {
  it('infers visualizer mode for character sheet payloads', () => {
    expect(inferVisualizerModeFromPayload({ mode: 'character_sheet_render' })).toBe('character_sheet_render')
    expect(inferVisualizerModeFromPayload({ asset_unit_kind: 'character_sheet' })).toBe('character_sheet_render')
    expect(inferVisualizerModeFromPayload({ asset_unit_kind: 'image' })).toBeNull()
    expect(inferVisualizerModeFromPayload({ prompt_text: '#Character2\nMode: character_sheet_render' })).toBe('character_sheet_render')
    expect(inferVisualizerModeFromPayload({ prompt_text: '#Slide1\n...' })).toBeNull()
  })

  it('merges writer and visual outputs into the active writer version', () => {
    const withWriter = mergeCharacterSheetBundleWithWriter(undefined, {
      artifact_id: 'step_11_story',
      output: {
        execution_summary: 'done',
        characters: [{ character_id: 'c1', name: 'A' }],
      },
      status: 'completed',
    })

    const withVisual = mergeCharacterSheetBundleWithVisual(withWriter, {
      artifact_id: 'step_12_visual',
      slide_number: 1,
      title: 'Character Sheet: A',
      image_url: 'https://example.com/a.png',
      status: 'completed',
      mode: 'character_sheet_render',
    })

    const normalized = normalizeCharacterSheetBundle(withVisual)
    expect(normalized.active_version_id).toBe('step_11_story')
    expect(normalized.versions).toHaveLength(1)

    const version = normalized.versions[0]
    expect(version.writer_artifact_id).toBe('step_11_story')
    expect(version.visual_runs).toHaveLength(1)
    expect(version.visual_runs[0].visual_artifact_id).toBe('step_12_visual')
    expect(version.visual_runs[0].slides).toHaveLength(1)
    expect(version.visual_runs[0].slides[0].image_url).toBe('https://example.com/a.png')
  })

  it('creates a pending placeholder version when visual output arrives before writer output', () => {
    const visualFirst = mergeCharacterSheetBundleWithVisual(undefined, {
      artifact_id: 'step_30_visual',
      slide_number: 1,
      title: 'Character Sheet: Pending',
      image_url: 'https://example.com/pending.png',
      status: 'streaming',
      mode: 'character_sheet_render',
    })

    const normalized = normalizeCharacterSheetBundle(visualFirst)
    expect(normalized.versions).toHaveLength(1)
    expect(normalized.versions[0].writer_status).toBe('pending')
    expect(normalized.active_version_id).toBe(`pending:step_30_visual`)
    expect(normalized.versions[0].visual_runs[0].slides[0].image_url).toBe('https://example.com/pending.png')
  })

  it('rebuilds bundle artifact from snapshot artifacts preserving version history', () => {
    const artifacts: Record<string, any> = {
      step_10_story: {
        id: 'step_10_story',
        type: 'writer_character_sheet',
        title: 'Character Sheet',
        content: {
          characters: [{ character_id: 'hero', name: 'Hero' }],
        },
        version: 1,
        status: 'completed',
      },
      step_11_visual: {
        id: 'step_11_visual',
        type: 'slide_deck',
        title: 'Generated Slides',
        content: {
          mode: 'character_sheet_render',
          slides: [
            {
              slide_number: 1,
              title: 'Character Sheet: Hero',
              image_url: 'https://example.com/hero.png',
              prompt_text: '#Character1\nMode: character_sheet_render',
              status: 'completed',
            },
          ],
        },
        version: 1,
        status: 'completed',
      },
      step_12_story: {
        id: 'step_12_story',
        type: 'writer_character_sheet',
        title: 'Character Sheet',
        content: {
          characters: [{ character_id: 'villain', name: 'Villain' }],
        },
        version: 1,
        status: 'completed',
      },
      step_13_visual: {
        id: 'step_13_visual',
        type: 'slide_deck',
        title: 'Generated Slides',
        content: {
          slides: [
            {
              slide_number: 1,
              title: 'Character Sheet: Villain',
              image_url: 'https://example.com/villain.png',
              prompt_text: '#Character1\nMode: character_sheet_render',
              status: 'completed',
            },
          ],
        },
        version: 1,
        status: 'completed',
      },
      step_20_visual: {
        id: 'step_20_visual',
        type: 'slide_deck',
        title: 'Generated Slides',
        content: {
          mode: 'slide_render',
          slides: [
            {
              slide_number: 1,
              title: 'Normal slide',
              image_url: 'https://example.com/slide.png',
              prompt_text: '#Slide1',
              status: 'completed',
            },
          ],
        },
        version: 1,
        status: 'completed',
      },
    }

    const bundleArtifact = buildCharacterSheetBundleArtifact(artifacts)
    expect(bundleArtifact).toBeTruthy()
    expect(bundleArtifact?.id).toBe(CHARACTER_SHEET_BUNDLE_ARTIFACT_ID)

    const bundle = normalizeCharacterSheetBundle(bundleArtifact?.content)
    expect(bundle.versions).toHaveLength(2)
    expect(bundle.versions[0].version_id).toBe('step_10_story')
    expect(bundle.versions[1].version_id).toBe('step_12_story')
    expect(bundle.active_version_id).toBe('step_12_story')

    expect(bundle.versions[0].visual_runs).toHaveLength(1)
    expect(bundle.versions[0].visual_runs[0].slides[0].image_url).toBe('https://example.com/hero.png')
    expect(bundle.versions[1].visual_runs).toHaveLength(1)
    expect(bundle.versions[1].visual_runs[0].slides[0].image_url).toBe('https://example.com/villain.png')
  })
})
