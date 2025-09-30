import Tesseract from 'tesseract.js';

export type OCRResult = { text: string };

export async function ocrImage(image: Buffer, lang = 'eng'): Promise<OCRResult> {
  const res = await Tesseract.recognize(image, lang, { /* options can be extended */ });
  return { text: res.data.text };
}

export function parseNumericFromText(text: string): number | null {
  const cleaned = text.replace(/[\s,]/g, '').replace(/\(([^)]+)\)/, '-$1');
  const m = cleaned.match(/-?\d+(?:\.\d+)?/);
  return m ? Number(m[0]) : null;
}
