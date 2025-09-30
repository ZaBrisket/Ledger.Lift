import { test, expect } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';
import PDFDocument from 'pdfkit';

function makePDF(tmpPath: string) {
  const doc = new PDFDocument({ size: 'A4', margin: 50 });
  const out = fs.createWriteStream(tmpPath);
  doc.pipe(out);
  doc.fontSize(16).text('Income Statement', { align: 'left' });
  doc.moveDown();
  doc.fontSize(12);
  doc.text('Metric        2024', 50, 150);
  doc.text('Revenue       1000', 50, 170);
  doc.text('EBITDA        250', 50, 190);
  doc.end();
  return new Promise<string>((resolve) => out.on('close', () => resolve(tmpPath)));
}

test('upload → status → download', async ({ page, tmpDir }) => {
  await page.goto('/convert');
  // create a temp pdf
  const f = path.join(tmpDir, 'tiny.pdf');
  await makePDF(f);

  const [fileChooser] = await Promise.all([
    page.waitForEvent('filechooser'),
    page.locator('input[type="file"]').click(),
  ]);
  await fileChooser.setFiles(f);

  await page.getByRole('button', { name: 'Start' }).click();
  await page.waitForTimeout(1000);

  // Wait for either error or success (download link appears)
  const link = page.locator('a', { hasText: 'Download Excel' });
  await expect(link).toBeVisible({ timeout: 120000 });
  const href = await link.getAttribute('href');
  expect(href).toContain('http');
});
