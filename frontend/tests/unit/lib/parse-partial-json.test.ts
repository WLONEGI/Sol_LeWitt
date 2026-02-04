import { describe, expect, it } from 'vitest';
import { parsePartialArray, parsePartialJSON } from '@/lib/utils/parse-partial-json';

describe('parsePartialJSON', () => {
  it('parses complete JSON as complete', () => {
    const input = '{"a":1,"b":[1,2]}';
    const result = parsePartialJSON(input);

    expect(result.isComplete).toBe(true);
    expect(result.parsed).toEqual({ a: 1, b: [1, 2] });
  });

  it('repairs incomplete JSON by auto-closing brackets', () => {
    const input = '{"a":1,"b":[1,2';
    const result = parsePartialJSON(input);

    expect(result.isComplete).toBe(false);
    expect(result.parsed).toEqual({ a: 1, b: [1, 2] });
  });

  it('returns null for non-string input', () => {
    // @ts-expect-error testing runtime guard
    const result = parsePartialJSON(null);

    expect(result.parsed).toBeNull();
    expect(result.isComplete).toBe(false);
  });
});

describe('parsePartialArray', () => {
  it('returns array for incomplete array JSON', () => {
    const input = '[{"id":1},{"id":2}';
    const result = parsePartialArray(input);

    expect(result).toEqual([{ id: 1 }, { id: 2 }]);
  });

  it('returns empty array when parsing fails', () => {
    const result = parsePartialArray('not-json');
    expect(result).toEqual([]);
  });
});
