import { CreateMultipartUploadCommand, PutObjectCommand, UploadPartCommand } from '@aws-sdk/client-s3';
import { getSignedUrl } from '@aws-sdk/s3-request-presigner';
import { z } from 'zod';
import { env } from '../../src/config/env';
import { getS3Client } from './_storage';
import { createHandler, parseJsonBody } from './_utils';

const uploadRequestSchema = z.object({
  filename: z.string().min(1, 'filename is required'),
  size: z.coerce
    .number({ invalid_type_error: 'size must be a number' })
    .int('size must be an integer')
    .positive('size must be positive'),
  contentType: z.string().min(1, 'contentType is required'),
  sha256: z
    .string()
    .regex(/^[a-fA-F0-9]{64}$/u, 'sha256 must be a 64 character hex string'),
  sha256Base64: z
    .string()
    .regex(/^[A-Za-z0-9+/]+={0,2}$/u, 'sha256Base64 must be a valid base64 checksum'),
});

const sanitizeFilename = (filename: string) =>
  filename
    .replace(/\\/g, '/')
    .split('/')
    .pop()!
    .replace(/[^A-Za-z0-9._-]+/g, '_')
    .slice(-120);

const MIN_PART_SIZE = 5 * 1024 * 1024; // 5MB S3 minimum
const MAX_PART_SIZE = 5 * 1024 * 1024 * 1024; // 5GB S3 maximum
const MAX_PARTS = 10_000; // S3 limit
const MAX_PROCESSABLE = MAX_PART_SIZE * MAX_PARTS; // 50TB

export const handler = createHandler(['POST'], async (event, _context, { json, requestId }) => {
  const payload = uploadRequestSchema.safeParse(parseJsonBody<unknown>(event));

  if (!payload.success) {
    return json(400, {
      ok: false,
      error: 'Invalid upload request',
      details: payload.error.flatten().fieldErrors,
      requestId,
    });
  }

  if (payload.data.contentType !== 'application/pdf') {
    return json(415, {
      ok: false,
      error: 'Only application/pdf uploads are supported at this time',
      requestId,
    });
  }

  if (payload.data.size > env.PDF_MAX_BYTES) {
    return json(413, {
      ok: false,
      error: `PDF exceeds maximum size of ${env.PDF_MAX_MB}MB`,
      requestId,
    });
  }

  const s3 = getS3Client();
  const safeFilename = sanitizeFilename(payload.data.filename);
  const sourceKey = `uploads/${payload.data.sha256}/${Date.now()}-${safeFilename}`;

  if (payload.data.size > MAX_PROCESSABLE) {
    return json(413, {
      ok: false,
      error: `File exceeds maximum size of ${MAX_PROCESSABLE / 1024 ** 4}TB`,
      requestId,
    });
  }

  const expiresIn = env.PRESIGN_TTL;

  if (payload.data.size < env.R2_MULTIPART_THRESHOLD_BYTES) {
    const command = new PutObjectCommand({
      Bucket: env.R2_BUCKET,
      Key: sourceKey,
      ContentType: payload.data.contentType,
      ChecksumSHA256: payload.data.sha256Base64,
    });

    const url = await getSignedUrl(s3, command, { expiresIn });

    return json(200, {
      ok: true,
      uploadType: 'single',
      url,
      sourceKey,
      expiresIn,
    });
  }

  const multipart = await s3.send(
    new CreateMultipartUploadCommand({
      Bucket: env.R2_BUCKET,
      Key: sourceKey,
      ContentType: payload.data.contentType,
    })
  );

  if (!multipart.UploadId) {
    throw new Error('Multipart upload could not be initiated');
  }

  let partSize = Math.max(
    MIN_PART_SIZE,
    env.R2_MULTIPART_THRESHOLD_BYTES,
    Math.ceil(payload.data.size / MAX_PARTS)
  );
  partSize = Math.min(partSize, MAX_PART_SIZE);
  partSize = Math.ceil(partSize / (1024 * 1024)) * (1024 * 1024);

  const partCount = Math.ceil(payload.data.size / partSize);

  const parts = await Promise.all(
    Array.from({ length: partCount }, async (_value, index) => {
      const partNumber = index + 1;
      const command = new UploadPartCommand({
        Bucket: env.R2_BUCKET,
        Key: sourceKey,
        UploadId: multipart.UploadId!,
        PartNumber: partNumber,
      });

      const url = await getSignedUrl(s3, command, { expiresIn });
      return { partNumber, url };
    })
  );

  return json(200, {
    ok: true,
    uploadType: 'multipart',
    uploadId: multipart.UploadId,
    parts,
    sourceKey,
    partSize,
    expiresIn,
  });
});
