import { Handler } from '@netlify/functions';
import { z } from 'zod';
import { env } from '../../src/config/env';
import { completeMultipartUpload } from '../../src/lib/storage/s3';
import { createJob } from '../../src/lib/jobs/repo';
import { corsHeaders, ok, error, preflight, correlationIdFrom } from '../../src/lib/http/httpUtils';

const Body = z.object({
  sourceKey: z.string().min(1),
  filename: z.string().min(1),
  size: z.number().int().positive(),
  // Optional finalize support for MPU
  uploadId: z.string().optional(),
  parts: z.array(z.object({ ETag: z.string(), PartNumber: z.number().int().positive() })).optional(),
});

export const handler: Handler = async (event, context) => {
  if (event.httpMethod === 'OPTIONS') return preflight(event.headers?.origin);
  try {
    const origin = event.headers?.origin;
    const corr = correlationIdFrom(event);
    const body = Body.parse(JSON.parse(event.body || '{}'));

    if (body.uploadId && body.parts?.length) {
      // finalize the multipart upload
      await completeMultipartUpload(body.sourceKey, body.uploadId, body.parts);
    }

    const jobId = `job_${Date.now()}_${Math.random().toString(16).slice(2)}`;
    const now = new Date().toISOString();
    await createJob({
      jobId,
      status: 'QUEUED',
      createdAt: now,
      updatedAt: now,
      sourceKey: body.sourceKey,
      filename: body.filename,
      size: body.size,
      progress: [{ step: 'QUEUED', pct: 1 }],
      corr,
    });

    // fire-and-forget background parse
    const siteUrl = process.env.URL || process.env.DEPLOY_URL || '';
    try {
      if (siteUrl) {
        await fetch(`${siteUrl}/.netlify/functions/parse-and-extract-background`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'x-correlation-id': corr },
          body: JSON.stringify({ jobId }),
        });
      }
    } catch {}

    return ok({ jobId }, origin);
  } catch (e: any) {
    return error(400, e?.message || 'Bad Request', event.headers?.origin);
  }
};
