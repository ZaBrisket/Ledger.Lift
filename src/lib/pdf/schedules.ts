import type { Table } from './tables';

export type Schedule = {
  type: 'Income Statement'|'Balance Sheet'|'Cash Flow'|'Unknown';
  confidence: number;
  table: Table;
};

const HEADINGS = [
  { type: 'Income Statement' as const, patterns: [/income\s+statement/i, /p\&l/i, /profit and loss/i] },
  { type: 'Balance Sheet' as const, patterns: [/balance\s+sheet/i] },
  { type: 'Cash Flow' as const, patterns: [/cash\s*flow/i] },
];

export function classifyTables(tables: Table[]): Schedule[] {
  return tables.map((t) => {
    // simple heading heuristic: look at first row cells concatenated
    const heading = t.cells[0]?.map(c => c.text).join(' ').slice(0, 200) || '';
    let best: { type: Schedule['type']; score: number } = { type: 'Unknown', score: 0 };
    for (const h of HEADINGS) {
      for (const p of h.patterns) {
        if (p.test(heading)) {
          best = { type: h.type, score: Math.max(best.score, 0.9) };
        }
      }
    }
    // if unidentified, use column keywords
    if (best.score === 0) {
      const texts = t.cells.flat().map(c => c.text.toLowerCase());
      const signals = [
        { type: 'Income Statement' as const, kw: ['revenue','gross','ebitda','net income'] },
        { type: 'Balance Sheet' as const, kw: ['assets','liabilities','equity'] },
        { type: 'Cash Flow' as const, kw: ['operating','investing','financing'] },
      ];
      for (const s of signals) {
        const hits = s.kw.filter(k => texts.some(t=>t.includes(k))).length;
        if (hits >= 2) { best = { type: s.type, score: 0.7 }; break; }
      }
    }
    return { type: best.type, confidence: best.score, table: t };
  }).filter(s => s.confidence >= 0.6);
}
