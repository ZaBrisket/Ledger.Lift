import { describe, it, expect } from 'vitest';
import PDFDocument from 'pdfkit';
import { extractGlyphs } from '../../src/lib/pdf/reader';
import { detectTables } from '../../src/lib/pdf/tables';

function makePDF(): Buffer {
  const doc = new PDFDocument({ size: 'A4', margin: 50 });
  const chunks: Buffer[] = [];
  doc.on('data', (c) => chunks.push(c));
  doc.on('end', () => {});

  doc.fontSize(16).text('Income Statement', { align: 'left' });
  doc.moveDown();
  doc.fontSize(12);
  doc.text('Metric        2024', 50, 150);
  doc.text('Revenue       1000', 50, 170);
  doc.text('EBITDA        250', 50, 190);

  doc.end();
  return Buffer.concat(chunks);
}

describe('integration: tiny synthetic PDF', () => {
  it('detects at least one table-like structure', async () => {
    const pdf = makePDF();
    const glyphs = await extractGlyphs(new Uint8Array(pdf));
    const tables = detectTables(glyphs, 8);
    expect(tables.length).toBeGreaterThanOrEqual(1);
  });
});
