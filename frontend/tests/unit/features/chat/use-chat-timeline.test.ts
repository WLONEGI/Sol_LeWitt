import { describe, expect, it } from 'vitest';
import { renderHook } from '@testing-library/react';

import { useChatTimeline } from '@/features/chat/hooks/use-chat-timeline';

function event(type: string, data: Record<string, unknown>, seq: number) {
  return {
    type,
    data,
    __seq: seq,
    __msgCount: 1,
  };
}

const baseMessages: any[] = [
  {
    id: 'u1',
    role: 'user',
    parts: [{ type: 'text', text: 'hello' }],
  },
];

describe('useChatTimeline aggregation', () => {
  it('prioritizes message-part ordering for step markers, text/reasoning, and custom data', () => {
    const messages: any[] = [
      ...baseMessages,
      {
        id: 'a1',
        role: 'assistant',
        parts: [
          { type: 'data-plan_step_started', data: { step_id: 1, title: 'Step 1' } },
          { type: 'text', text: 'alpha' },
          { type: 'reasoning', text: 'thinking' },
          {
            type: 'data-image-search-results',
            data: {
              task_id: 't1',
              query: 'query',
              candidates: [],
            },
          },
          { type: 'text', text: 'beta' },
          { type: 'data-plan_step_ended', data: { step_id: 1 } },
        ],
      },
    ];

    // Include stream data as well to ensure we do not duplicate when data-* parts exist in messages.
    const data = [
      event('data-plan_step_started', { step_id: 1, title: 'Step 1' }, 1),
      event('data-plan_step_ended', { step_id: 1 }, 2),
    ];

    const { result } = renderHook(() => useChatTimeline(messages, data));
    const timeline = result.current.timeline;

    const stepStartCount = timeline.filter((item) => item.type === 'plan_step_marker').length;
    const stepEndCount = timeline.filter((item) => item.type === 'plan_step_end_marker').length;
    expect(stepStartCount).toBe(1);
    expect(stepEndCount).toBe(1);

    const stepScoped = timeline.filter((item) => item.timestamp >= 1000);
    expect(stepScoped.map((item) => item.type)).toEqual([
      'plan_step_marker',
      'message',
      'message',
      'image_search_results',
      'message',
      'plan_step_end_marker',
    ]);

    const messageContents = stepScoped
      .filter((item: any) => item.type === 'message')
      .map((item: any) => item.message.content || item.message.reasoning);
    expect(messageContents).toEqual(['alpha', 'thinking', 'beta']);
  });

  it('keeps one latest slide outline per artifact id', () => {
    const data = [
      event(
        'data-outline',
        {
          artifact_id: 'step_1_story',
          title: 'Slide Outline',
          slides: [{ slide_number: 1, title: 'old-outline', bullet_points: [] }],
        },
        1
      ),
      event(
        'data-outline',
        {
          artifact_id: 'step_1_story',
          title: 'Slide Outline',
          slides: [{ slide_number: 1, title: 'new-outline', bullet_points: [] }],
        },
        2
      ),
      event(
        'data-outline',
        {
          artifact_id: 'step_2_story',
          title: 'Slide Outline',
          slides: [{ slide_number: 1, title: 'other-outline', bullet_points: [] }],
        },
        3
      ),
    ];

    const { result } = renderHook(() => useChatTimeline(baseMessages, data));
    const outlines = result.current.timeline.filter((item) => item.type === 'slide_outline') as any[];

    expect(outlines).toHaveLength(2);
    const flattenedTitles = outlines.flatMap((item) =>
      Array.isArray(item.slides) ? item.slides.map((s: any) => s.title) : []
    );
    expect(flattenedTitles).toContain('new-outline');
    expect(flattenedTitles).toContain('other-outline');
    expect(flattenedTitles).not.toContain('old-outline');
  });

  it('keeps one latest writer artifact per artifact id and ignores writer outline type', () => {
    const data = [
      event(
        'data-writer-output',
        {
          artifact_id: 'step_10_story',
          artifact_type: 'writer_story_framework',
          title: 'Writer V1',
        },
        1
      ),
      event(
        'data-writer-output',
        {
          artifact_id: 'step_10_story',
          artifact_type: 'writer_story_framework',
          title: 'Writer V2',
        },
        2
      ),
      event(
        'data-writer-output',
        {
          artifact_id: 'step_11_story',
          artifact_type: 'writer_character_sheet',
          title: 'Writer Character',
        },
        3
      ),
      event(
        'data-writer-output',
        {
          artifact_id: 'step_12_story',
          artifact_type: 'outline',
          title: 'Outline should be ignored',
        },
        4
      ),
    ];

    const { result } = renderHook(() => useChatTimeline(baseMessages, data));
    const writerArtifacts = result.current.timeline.filter(
      (item: any) => item.type === 'artifact' && item.icon === 'BookOpen'
    ) as any[];

    expect(writerArtifacts).toHaveLength(2);
    const step10 = writerArtifacts.find((item) => item.artifactId === 'step_10_story');
    expect(step10).toBeTruthy();
    expect(step10.title).toBe('Writer V2');
    expect(step10.kind).toBe('writer_story_framework');
    expect(writerArtifacts.some((item) => item.title === 'Writer V1')).toBe(false);
    expect(
      writerArtifacts.some((item) => item.artifactId === 'step_12_story')
    ).toBe(false);
  });

  it('keeps one latest image search result per artifact key and preserves multiple keys', () => {
    const data = [
      event(
        'data-image-search-results',
        {
          artifact_id: 'step_3_research_1',
          task_id: 'r1',
          query: 'q-old',
          perspective: 'p1',
          candidates: [
            {
              image_url: 'https://example.com/old.png',
              source_url: 'https://example.com/src-old',
              license_note: 'CC BY 4.0',
            },
          ],
        },
        1
      ),
      event(
        'data-image-search-results',
        {
          artifact_id: 'step_3_research_1',
          task_id: 'r1',
          query: 'q-new',
          perspective: 'p1',
          candidates: [
            {
              image_url: 'https://example.com/new.png',
              source_url: 'https://example.com/src-new',
              license_note: 'CC BY-SA 4.0',
            },
          ],
        },
        2
      ),
      event(
        'data-image-search-results',
        {
          artifact_id: 'step_3_research_2',
          task_id: 'r2',
          query: 'q-other',
          perspective: 'p2',
          candidates: [
            {
              image_url: 'https://example.com/other.png',
              source_url: 'https://example.com/src-other',
              license_note: 'CC0',
            },
          ],
        },
        3
      ),
    ];

    const { result } = renderHook(() => useChatTimeline(baseMessages, data));
    const imageSearchItems = result.current.timeline.filter(
      (item) => item.type === 'image_search_results'
    ) as any[];

    expect(imageSearchItems).toHaveLength(2);
    const updated = imageSearchItems.find((item) => item.artifactId === 'step_3_research_1');
    expect(updated).toBeTruthy();
    expect(updated.query).toBe('q-new');
    expect(updated.candidates?.[0]?.image_url).toBe('https://example.com/new.png');
    expect(updated.candidates?.[0]?.image_url).not.toBe('https://example.com/old.png');
    expect(
      imageSearchItems.some((item) => item.artifactId === 'step_3_research_2')
    ).toBe(true);
  });

  it('adds coordinator follow-up options as timeline item', () => {
    const messages: any[] = [
      ...baseMessages,
      {
        id: 'a1',
        role: 'assistant',
        parts: [{ type: 'text', text: '要件を明確化するため質問です。' }],
      },
    ];

    const data = [
      event(
        'data-coordinator-followups',
        {
          question: '要件を明確化するため質問です。',
          options: [
            { id: 'f1', prompt: '目的は〇〇です。' },
            { id: 'f2', prompt: '範囲は〇〇です。' },
            { id: 'f3', prompt: '制約は〇〇です。' },
          ],
        },
        1
      ),
    ];

    const { result } = renderHook(() => useChatTimeline(messages, data));
    const followups = result.current.timeline.filter(
      (item: any) => item.type === 'coordinator_followups'
    ) as any[];

    expect(followups).toHaveLength(1);
    expect(followups[0].options).toHaveLength(3);
    expect(followups[0].options[0].prompt).toBe('目的は〇〇です。');
    expect(followups[0].timestamp).toBeGreaterThan(1000);
  });
});
