import { describe, expect, it } from 'vitest'

import { resolveDataEventMessageCount } from '@/features/chat/lib/data-event-order'

describe('resolveDataEventMessageCount', () => {
    it('uses explicit override first', () => {
        const result = resolveDataEventMessageCount({
            messageCountOverride: 10,
            streamMessageCount: 4,
            currentMessageCount: 7,
        })

        expect(result).toBe(10)
    })

    it('uses stream anchor while streaming even if current message count increased', () => {
        const result = resolveDataEventMessageCount({
            streamMessageCount: 4,
            currentMessageCount: 5,
        })

        expect(result).toBe(4)
    })

    it('falls back to current message count when no override and no stream anchor', () => {
        const result = resolveDataEventMessageCount({
            currentMessageCount: 3,
        })

        expect(result).toBe(3)
    })
})
