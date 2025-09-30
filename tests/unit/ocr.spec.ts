import { describe, it, expect } from 'vitest';
import { parseNumericFromText } from '../../src/lib/pdf/ocr';

describe('ocr numeric cleanup', () => {
  it('parses negative and thousand-separated numbers', () => {
    expect(parseNumericFromText('1,234')).toBe(1234);
    expect(parseNumericFromText('(123)')).toBe(-123);
    expect(parseNumericFromText('foo 99.5 bar')).toBe(99.5);
  });
});
