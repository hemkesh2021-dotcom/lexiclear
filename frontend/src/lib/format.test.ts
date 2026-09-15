import { describe, expect, it } from 'vitest';

import { humaniseCategory } from '@/lib/format';

describe('humaniseCategory', () => {
  it.each([
    ['restrictive_covenant', 'Restrictive covenant'],
    ['intellectual_property', 'Intellectual property'],
    ['payment', 'Payment'],
    ['other', 'Other'],
  ])('renders %s as %s', (input, expected) => {
    expect(humaniseCategory(input)).toBe(expected);
  });

  it('leaves an empty string empty', () => {
    expect(humaniseCategory('')).toBe('');
  });
});
