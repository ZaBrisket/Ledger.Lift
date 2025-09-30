import * as pdfjs from 'pdfjs-dist';

// In Node/Netlify runtime we rely on the built-in worker-less mode.
(pdfjs as any).GlobalWorkerOptions.workerSrc = undefined;

export type Glyph = { text: string; x: number; y: number; fontSize: number; width: number; height: number; page: number };

export async function loadPdf(data: Uint8Array) {
  const doc = await (pdfjs as any).getDocument({ data, useSystemFonts: true, isEvalSupported: false }).promise;
  return doc;
}

export async function extractGlyphs(data: Uint8Array, maxPages?: number): Promise<Glyph[]> {
  const doc = await loadPdf(data);
  const pageCount = doc.numPages;
  const glyphs: Glyph[] = [];
  const pages = maxPages ? Math.min(pageCount, maxPages) : pageCount;

  for (let i = 1; i <= pages; i++) {
    const page = await doc.getPage(i);
    const viewport = page.getViewport({ scale: 1 });
    const content = await page.getTextContent();
    for (const item of content.items) {
      const it: any = item;
      const tx = it.transform; // [a, b, c, d, e, f]
      const fontSize = Math.hypot(tx[0], tx[3]);
      const x = tx[4];
      const y = viewport.height - tx[5];
      const text = it.str as string;
      const width = it.width;
      const height = it.height || fontSize * 1.2;
      glyphs.push({ text, x, y, fontSize, width, height, page: i });
    }
  }
  return glyphs;
}
