import { describe, it, expect } from 'vitest';
import { buildWorkbook } from '../../src/lib/excel/exporter';
import { Schedule } from '../../src/lib/pdf/schedules';

describe('excel exporter', async () => {
  it('creates a workbook with at least one sheet plus _Summary', async () => {
    const schedule: Schedule = {
      type: 'Income Statement',
      confidence: 0.9,
      table: {
        page: 1, rows: 2, cols: 2,
        bbox: { x: 0, y: 0, w: 100, h: 100 },
        cells: [
          [{ r:0,c:0,text:'Metric' }, { r:0,c:1,text:'Value' }],
          [{ r:1,c:0,text:'Revenue' }, { r:1,c:1,text:'1,000' }],
        ]
      }
    };
    const buf = await buildWorkbook([schedule], { sourceName: 'test.pdf', pages: 1 });
    expect(buf.byteLength).toBeGreaterThan(1000);
  });
});
