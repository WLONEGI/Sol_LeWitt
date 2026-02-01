import { describe, it, expect } from 'vitest';
import { parsePartialJSON, parsePartialArray } from '@/lib/utils/parse-partial-json';

describe('parsePartialJSON', () => {
    it('parses complete JSON correctly', () => {
        const input = '{"name": "test", "value": 123}';
        const result = parsePartialJSON(input);

        expect(result.isComplete).toBe(true);
        expect(result.parsed).toEqual({ name: 'test', value: 123 });
    });

    it('parses complete array correctly', () => {
        const input = '[{"id": 1}, {"id": 2}]';
        const result = parsePartialJSON(input);

        expect(result.isComplete).toBe(true);
        expect(result.parsed).toEqual([{ id: 1 }, { id: 2 }]);
    });

    it('auto-closes incomplete object with missing brace', () => {
        const input = '{"name": "test"';
        const result = parsePartialJSON(input);

        expect(result.isComplete).toBe(false);
        expect(result.parsed).toEqual({ name: 'test' });
    });

    it('auto-closes incomplete array with missing bracket', () => {
        const input = '[{"id": 1}, {"id": 2}';
        const result = parsePartialJSON(input);

        expect(result.isComplete).toBe(false);
        expect(result.parsed).toEqual([{ id: 1 }, { id: 2 }]);
    });

    it('handles trailing comma before auto-close', () => {
        const input = '{"items": [1, 2, 3,';
        const result = parsePartialJSON(input);

        expect(result.isComplete).toBe(false);
        expect(result.parsed).toEqual({ items: [1, 2, 3] });
    });

    it('handles deeply nested incomplete structures', () => {
        const input = '{"level1": {"level2": {"level3": "value"';
        const result = parsePartialJSON(input);

        expect(result.isComplete).toBe(false);
        expect(result.parsed).toEqual({ level1: { level2: { level3: 'value' } } });
    });

    it('returns null for unrecoverable input', () => {
        const input = '{"name": test}'; // Invalid: unquoted string
        const result = parsePartialJSON(input);

        expect(result.parsed).toBe(null);
        expect(result.isComplete).toBe(false);
    });

    it('returns null for empty input', () => {
        expect(parsePartialJSON('').parsed).toBe(null);
        expect(parsePartialJSON(null as any).parsed).toBe(null);
        expect(parsePartialJSON(undefined as any).parsed).toBe(null);
    });

    it('handles mixed brackets and braces', () => {
        const input = '[{"steps": [{"id": 1';
        const result = parsePartialJSON(input);

        expect(result.isComplete).toBe(false);
        expect(result.parsed).toEqual([{ steps: [{ id: 1 }] }]);
    });
});

describe('parsePartialArray', () => {
    it('returns array from complete JSON array', () => {
        const result = parsePartialArray('[1, 2, 3]');
        expect(result).toEqual([1, 2, 3]);
    });

    it('returns array from incomplete JSON array', () => {
        const result = parsePartialArray('[{"id": 1}, {"id": 2');
        expect(result).toEqual([{ id: 1 }, { id: 2 }]);
    });

    it('returns empty array for non-array JSON', () => {
        const result = parsePartialArray('{"key": "value"}');
        expect(result).toEqual([]);
    });

    it('returns empty array for invalid input', () => {
        const result = parsePartialArray('not json');
        expect(result).toEqual([]);
    });
});
