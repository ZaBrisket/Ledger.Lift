import ExcelJS from 'exceljs';
import type { Schedule } from '../pdf/schedules';

function sanitizeSheetName(name: string) {
  return name.replace(/[\\/*?:\[\]]/g, '_').slice(0, 31) || 'Sheet';
}

export async function buildWorkbook(schedules: Schedule[], meta: { sourceName: string; pages: number }) {
  const wb = new ExcelJS.Workbook();
  wb.creator = 'Ledger Lift';
  wb.created = new Date();

  const s = wb.addWorksheet('_Summary');
  s.getCell('A1').value = 'Source';
  s.getCell('B1').value = meta.sourceName;
  s.getCell('A2').value = 'Pages processed';
  s.getCell('B2').value = meta.pages;
  s.getRow(1).font = { bold: true };
  s.getRow(2).font = { bold: true };

  for (const sch of schedules) {
    const name = sanitizeSheetName(`${sch.type}`);
    const ws = wb.addWorksheet(name);
    // header
    const header = sch.table.cells[0].map(c => c.text || '');
    ws.addRow(header);
    ws.getRow(1).font = { bold: true };
    ws.autoFilter = { from: { row:1, column:1 }, to: { row:1, column: header.length } };
    ws.views = [{ state: 'frozen', ySplit: 1 }];

    for (let r = 1; r < sch.table.cells.length; r++) {
      const row = sch.table.cells[r];
      const values = row.map(c => {
        const n = Number(c.text.replace(/[\s,]/g, '').replace(/\(([^)]+)\)/, '-$1'));
        return Number.isFinite(n) ? n : (c.text || '');
      });
      ws.addRow(values);
    }
    // attempt basic numeric typing and width
    ws.columns?.forEach(col => { col.width = Math.min(40, Math.max(12, (col.header?.toString()?.length || 12))); });
  }

  const buf = await wb.xlsx.writeBuffer();
  return Buffer.from(buf);
}
