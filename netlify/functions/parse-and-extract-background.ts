import { Handler } from '@netlify/functions';
import { z } from 'zod';
import { getJob, updateJob, log } from '../../src/lib/jobs/repo';
import { getObjectBytes, putJson } from '../../src/lib/storage/s3';
import { extractGlyphs } from '../../src/lib/pdf/reader';
import { detectTables, normalizeTableNumbers } from '../../src/lib/pdf/tables';
import { classifyTables } from '../../src/lib/pdf/schedules';
import { buildWorkbook } from '../../src/lib/excel/exporter';
import { preflight, ok, error, correlationIdFrom } from '../../src/lib/http/httpUtils';
import { fileTypeFromBuffer } from 'file-type';

const Body = z.object({ jobId: z.string().min(1) });

export const handler: Handler = async (event) => {
  if (event.httpMethod === 'OPTIONS') return preflight(event.headers?.origin);
  const origin = event.headers?.origin;
  try {
    const { jobId } = Body.parse(JSON.parse(event.body || '{}'));
    const corr = correlationIdFrom(event);
    const job = await getJob(jobId);
    if (!job) return error(404, 'Job not found', origin);

    await updateJob(jobId, { status: 'PROCESSING', progress: [{ step: 'DOWNLOAD', pct: 10 }], corr });

    // download and sniff
    const pdfBytes = await getObjectBytes(job.sourceKey);
    const ft = await fileTypeFromBuffer(Buffer.from(pdfBytes));
    if (!ft || ft.mime !== 'application/pdf') {
      await updateJob(jobId, { status: 'ERROR', error: { code: 'NOT_PDF', message: 'Uploaded file is not a PDF' } });
      return ok({ ok: true }, origin,);
    }

    await updateJob(jobId, { progress: [{ step: 'PARSE_PDF', pct: 25 }] });
    const glyphs = await extractGlyphs(pdfBytes);
    await updateJob(jobId, { progress: [{ step: 'DETECT_TABLES', pct: 45 }] });

    const tables = detectTables(glyphs).map(normalizeTableNumbers);
    await updateJob(jobId, { progress: [{ step: 'CLASSIFY', pct: 65 }] });

    const schedules = classifyTables(tables);
    if (schedules.length === 0) {
      await updateJob(jobId, { status: 'ERROR', error: { code: 'NO_SCHEDULES', message: 'No schedules detected' } });
      return ok({ ok: true }, origin);
    }

    await updateJob(jobId, { progress: [{ step: 'EXPORT_EXCEL', pct: 85 }] });
    const workbook = await buildWorkbook(schedules, { sourceName: job.filename || 'source.pdf', pages: new Set(glyphs.map(g=>g.page)).size });
    const exportKey = `exports/${jobId}.xlsx`;
    await putJson(`processed/${jobId}.meta.json`, { pages: new Set(glyphs.map(g=>g.page)).size, tables: tables.length, schedules: schedules.length });
    // upload xlsx
    // We use putJson-like, but write object via S3 PutObject (reuse storage layer if needed)
    const { s3 } = await import('../../src/lib/storage/s3');
    const { PutObjectCommand } = await import('@aws-sdk/client-s3');
    const { env } = await import('../../src/config/env');
    await s3().send(new PutObjectCommand({ Bucket: env.R2_BUCKET, Key: exportKey, Body: workbook, ContentType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' }));

    await updateJob(jobId, { status: 'DONE', exportKey, progress: [{ step: 'DONE', pct: 100 }] });

    return ok({ ok: true, jobId }, origin);
  } catch (e: any) {
    const msg = e?.message || 'Unhandled error';
    // best-effort job update if possible
    try {
      const parsed = JSON.parse(event.body || '{}');
      if (parsed?.jobId) await updateJob(parsed.jobId, { status: 'ERROR', error: { code: 'EXTRACT_FAIL', message: msg } });
    } catch {}
    return error(500, msg, origin);
  }
};
