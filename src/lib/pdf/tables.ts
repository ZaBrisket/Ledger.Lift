import type { Glyph } from './reader';

export type TableCell = { r: number; c: number; text: string };
export type Table = { page: number; rows: number; cols: number; cells: TableCell[][]; bbox: { x: number; y: number; w: number; h: number } };

// Heuristic: cluster glyphs by y into rows, by x into columns, using k-means-like binning.
export function detectTables(glyphs: Glyph[], gridTolerance = 3): Table[] {
  const byPage = new Map<number, Glyph[]>();
  glyphs.forEach(g => {
    if (!byPage.has(g.page)) byPage.set(g.page, []);
    byPage.get(g.page)!.push(g);
  });

  const tables: Table[] = [];
  for (const [page, items] of byPage) {
    // Sort by y then x
    items.sort((a,b) => (a.y - b.y) || (a.x - b.x));

    // Row clustering: group lines with near-equal y baseline
    const rows: Glyph[][] = [];
    for (const g of items) {
      const r = rows.find(arr => Math.abs(arr[0].y - g.y) <= gridTolerance);
      if (r) r.push(g); else rows.push([g]);
    }

    // Filter rows that look like header + at least one data row (min 2 rows)
    if (rows.length < 2) continue;

    // Estimate columns from the widest row
    const widest = rows.reduce((acc, row) => row.length > acc.length ? row : acc, rows[0]);
    const colXs: number[] = [];
    for (const g of widest) {
      // add new column if gap from last > tolerance
      const last = colXs[colXs.length-1];
      if (!last || Math.abs(g.x - last) > 20) colXs.push(g.x);
    }
    const cols = colXs.length;
    if (cols < 2) continue;

    // Build grid text by snapping each glyph to nearest row/col
    const grid: string[][] = Array.from({ length: rows.length }, () => Array.from({ length: cols }, () => ''));
    rows.forEach((row, r) => {
      row.sort((a,b)=>a.x-b.x);
      for (const g of row) {
        let c = 0;
        let best = Infinity;
        for (let i = 0; i < cols; i++) {
          const d = Math.abs(g.x - colXs[i]);
          if (d < best) { best = d; c = i; }
        }
        grid[r][c] = (grid[r][c] ? grid[r][c] + ' ' : '') + g.text;
      }
    });

    // Compute bounding box
    const xs = items.map(i=>i.x);
    const ys = items.map(i=>i.y);
    const bbox = {
      x: Math.min(...xs),
      y: Math.min(...ys),
      w: Math.max(...xs) - Math.min(...xs),
      h: Math.max(...ys) - Math.min(...ys),
    };

    const cells = grid.map((row, r) => row.map((text, c) => ({ r, c, text })));
    tables.push({ page, rows: grid.length, cols, cells, bbox });
  }
  return tables;
}

export function normalizeTableNumbers(tbl: Table): Table {
  // Convert common numeric formats to JS numbers within text
  const cells = tbl.cells.map(row => row.map(cell => {
    const cleaned = cell.text.replace(/[, ]/g, '').replace(/\(([^)]+)\)/, '-$1');
    return { ...cell, text: cleaned };
  }));
  return { ...tbl, cells };
}
