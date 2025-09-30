import { describe, it, expect } from 'vitest';
import { detectTables, normalizeTableNumbers } from '../../src/lib/pdf/tables';

describe('tables', () => {
  it('builds a grid from glyphs', () => {
    const glyphs = [
      // header row (y ~ 10)
      { text: 'ColA', x: 10, y: 10, fontSize: 10, width: 20, height: 10, page: 1 },
      { text: 'ColB', x: 60, y: 10, fontSize: 10, width: 20, height: 10, page: 1 },
      // row 1 (y ~ 30)
      { text: '1', x: 10, y: 30, fontSize: 10, width: 10, height: 10, page: 1 },
      { text: '2', x: 60, y: 30, fontSize: 10, width: 10, height: 10, page: 1 },
    ] as any;
    const tables = detectTables(glyphs, 5);
    expect(tables.length).toBeGreaterThan(0);
    const t = normalizeTableNumbers(tables[0]);
    expect(t.rows).toBeGreaterThanOrEqual(2);
    expect(t.cols).toBe(2);
  });
});
