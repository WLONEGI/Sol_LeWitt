import { describe, expect, it } from 'vitest';
import { cn } from '@/lib/utils';

describe('cn', () => {
  it('merges class names and removes falsy values', () => {
    expect(cn('a', false && 'b', 'c')).toBe('a c');
  });

  it('resolves Tailwind class conflicts', () => {
    expect(cn('p-2', 'p-4')).toBe('p-4');
  });
});
