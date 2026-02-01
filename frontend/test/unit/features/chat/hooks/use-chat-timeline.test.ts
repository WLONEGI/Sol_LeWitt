import { renderHook } from '@testing-library/react';
import { useChatTimeline } from '@/features/chat/hooks/use-chat-timeline';
import { describe, it, expect } from 'vitest';
import { ProcessTimelineItem } from '@/features/chat/types/timeline';

describe('useChatTimeline', () => {
    it('1. 初期状態: タイムラインが空であること', () => {
        const { result } = renderHook(() => useChatTimeline([]));
        expect(result.current.timeline).toEqual([]);
    });

    it('2. 新規ステップ追加: timeline_updateイベントでタイムラインに追加されること', () => {
        const { result, rerender } = renderHook(({ data }) => useChatTimeline([], data), {
            initialProps: { data: [] as any[] }
        });

        const newEvent = {
            type: 'timeline_update',
            step_id: 'step-123',
            status: 'in_progress',
            label: 'Researching',
            details: 'Checking data...'
        };

        rerender({ data: [newEvent] });

        const timeline = result.current.timeline;
        expect(timeline).toHaveLength(1);
        const item = timeline[0] as ProcessTimelineItem;

        expect(item.type).toBe('process_step');
        expect(item.step.id).toBe('step-123');
        expect(item.step.status).toBe('running');
        expect(item.step.title).toBe('Researching');
        expect(item.step.description).toBe('Checking data...');
    });

    it('3. ステップ更新: 既存のstep_idを持つイベントで項目が更新されること', () => {
        const { result, rerender } = renderHook(({ data }) => useChatTimeline([], data), {
            initialProps: { data: [] as any[] }
        });

        const event1 = {
            type: 'timeline_update',
            step_id: 'step-123',
            status: 'in_progress',
            label: 'Start'
        };

        // First render
        rerender({ data: [event1] });

        const event2 = {
            type: 'timeline_update',
            step_id: 'step-123',
            status: 'completed',
            label: 'Done' // Usually title comes from label or title prop
        };

        // Second render (append to data array, simulating useChat behavior)
        rerender({ data: [event1, event2] });

        const timeline = result.current.timeline;
        expect(timeline).toHaveLength(1); // Should still be 1 (update)
        const item = timeline[0] as ProcessTimelineItem;

        expect(item.step.id).toBe('step-123');
        expect(item.step.status).toBe('completed');
        // promptLabelToTitle handles label -> title
        expect(item.step.title).toBe('Done');
        expect(item.step.expanded).toBe(false);
    });

    it('4. 順序保証: 複数のステップが正しい順序で保持されること', () => {
        const { result, rerender } = renderHook(({ data }) => useChatTimeline([], data), {
            initialProps: { data: [] as any[] }
        });

        const stepA = {
            type: 'timeline_update',
            step_id: 'step-A',
            status: 'in_progress',
            label: 'Step A'
        };
        const stepB = {
            type: 'timeline_update',
            step_id: 'step-B',
            status: 'in_progress',
            label: 'Step B'
        };

        rerender({ data: [stepA, stepB] });

        const timeline = result.current.timeline;
        expect(timeline).toHaveLength(2);
        expect((timeline[0] as ProcessTimelineItem).step.id).toBe('step-A');
        expect((timeline[1] as ProcessTimelineItem).step.id).toBe('step-B');
    });

    it('5. 無関係なデータの無視: timeline_update以外のデータは影響しないこと', () => {
        const { result, rerender } = renderHook(({ data }) => useChatTimeline([], data), {
            initialProps: { data: [] as any[] }
        });

        const randomEvent = {
            type: 'random_event',
            content: 'ignore me'
        };

        rerender({ data: [randomEvent] });

        expect(result.current.timeline).toEqual([]);
    });
});
