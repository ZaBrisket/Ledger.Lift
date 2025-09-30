import { CompleteMultipartUploadCommand } from '@aws-sdk/client-s3';
import { z } from 'zod';
import { env } from '../../src/config/env';
import { getS3Client } from './_storage';
import { createHandler, parseJsonBody } from './_utils';

const partSchema = z.object({
  partNumber: z.coerce
    .number({ invalid_type_error: 'partNumber must be a number' })
    .int('partNumber must be an integer')
    .positive('partNumber must be greater than zero'),
  etag: z.string().min(1, 'etag is required'),
});

const completionSchema = z.object({
  uploadId: z.string().min(1, 'uploadId is required'),
  sourceKey: z.string().min(1, 'sourceKey is required'),
  parts: z.array(partSchema).min(1, 'At least one part is required'),
});

export const handler = createHandler(['POST'], async (event, _context, { json, requestId }) => {
  const payload = completionSchema.safeParse(parseJsonBody<unknown>(event));

  if (!payload.success) {
    return json(400, {
      ok: false,
      error: 'Invalid completion payload',
      details: payload.error.flatten().fieldErrors,
      requestId,
    });
  }

  if (!/^uploads\/[a-f0-9]{64}\//iu.test(payload.data.sourceKey)) {
    return json(400, {
      ok: false,
      error: 'Invalid sourceKey',
      requestId,
    });
  }

  const normalizeEtag = (etag: string) => etag.replace(/^"|"$/g, '');

  const orderedParts = [...payload.data.parts].sort((a, b) => a.partNumber - b.partNumber);

  const client = getS3Client();
  const response = await client.send(
    new CompleteMultipartUploadCommand({
      Bucket: env.R2_BUCKET,
      Key: payload.data.sourceKey,
      UploadId: payload.data.uploadId,
      MultipartUpload: {
        Parts: orderedParts.map((part) => ({
          ETag: normalizeEtag(part.etag),
          PartNumber: part.partNumber,
        })),
      },
    })
  );

  return json(200, {
    ok: true,
    eTag: response.ETag ?? null,
    requestId,
  });
});
