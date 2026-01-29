import { describe, it, expect } from 'vitest'
import { cn } from './utils'

describe('cn utility', () => {
    it('should merge class names correctly', () => {
        expect(cn('c-1', 'c-2')).toBe('c-1 c-2')
    });

    it('should resolve tailwind conflicts', () => {
        expect(cn('p-2', 'p-4')).toBe('p-4')
        expect(cn('text-red-500', 'text-blue-500')).toBe('text-blue-500')
    });

    it('should handle conditional classes', () => {
        expect(cn('c-1', true && 'c-2', false && 'c-3')).toBe('c-1 c-2')
    });
});
