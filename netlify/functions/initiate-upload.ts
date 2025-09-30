import { Handler } from '@netlify/functions';
import { z } from 'zod';
import { env } from '../../src/config/env';
import { planMultipartUpload } from '../../src/lib/storage/s3';
import { corsHeaders, ok, error, preflight, correlationIdFrom } from '../../src/lib/http/httpUtils';

const Body = z.object({
  filename: z.string().min(1),
  size: z.number().int().positive(),
  contentType: z.string().default('application/pdf'),
  sha256: z.string().optional(), // informational only
});

function sanitizeFilename(name: string) {
  return name.replace(/[^A-Za-z0-9._-]+/g, '_').slice(0, 180);
}

export const handler: Handler = async (event, context) => {
  if (event.httpMethod === 'OPTIONS') return preflight(event.headers?.origin);
  try {
    const origin = event.headers?.origin;
    const corr = correlationIdFrom(event);
    const body = Body.parse(JSON.parse(event.body || '{}'));
    const maxBytes = env.PDF_MAX_MB * 1024 * 1024;
    if (body.size > maxBytes) {
      return error(413, `File exceeds limit of ${env.PDF_MAX_MB} MB`, origin, { code: 'SIZE_LIMIT' });
    }
    const filename = sanitizeFilename(body.filename);
    const sourceKey = `incoming/${Date.now()}_${filename}`;

    const plan = await planMultipartUpload(sourceKey, body.size, body.contentType);
    return ok({ sourceKey, uploadId: plan.uploadId, partSize: plan.partSize, parts: plan.parts }, origin);
  } catch (e: any) {
    return error(400, e?.message || 'Bad Request', event.headers?.origin);
  }
};
