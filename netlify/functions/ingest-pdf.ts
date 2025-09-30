import { GetObjectCommand, HeadObjectCommand } from '@aws-sdk/client-s3';
import { randomUUID } from 'crypto';
import { z } from 'zod';
import { env } from '../../src/config/env';
import { getS3Client } from './_storage';
import { createHandler, parseJsonBody } from './_utils';

const ingestSchema = z.object({
  sourceKey: z.string().min(1, 'sourceKey is required'),
  filename: z.string().min(1, 'filename is required'),
  size: z.coerce
    .number({ invalid_type_error: 'size must be a number' })
    .int('size must be an integer')
    .positive('size must be positive'),
});

async function streamToBuffer(stream: unknown): Promise<Buffer> {
  if (!stream) {
    return Buffer.alloc(0);
  }

  if (typeof Blob !== 'undefined' && stream instanceof Blob) {
    return Buffer.from(await stream.arrayBuffer());
  }

  if (typeof (stream as any).getReader === 'function') {
    const reader = (stream as any).getReader();
    const chunks: Uint8Array[] = [];
    let result = await reader.read();
    while (!result.done) {
      chunks.push(result.value);
      result = await reader.read();
    }
    return Buffer.concat(chunks.map((chunk) => Buffer.from(chunk)));
  }

  return new Promise<Buffer>((resolve, reject) => {
    const chunks: Buffer[] = [];
    (stream as NodeJS.ReadableStream)
      .on('data', (chunk) => chunks.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk)))
      .once('error', reject)
      .once('end', () => resolve(Buffer.concat(chunks)));
  });
}

type FileTypeCheck = (buffer: Buffer) => Promise<{ mime: string } | null>;

let cachedDetector: FileTypeCheck | null = null;

async function loadFileTypeDetector(): Promise<FileTypeCheck> {
  if (cachedDetector) {
    return cachedDetector;
  }

  try {
    const mod: any = await import('file-type');
    const detector: ((buffer: Buffer) => Promise<{ mime: string } | null>) | undefined =
      typeof mod.fileTypeFromBuffer === 'function'
        ? mod.fileTypeFromBuffer
        : typeof mod.default?.fileTypeFromBuffer === 'function'
        ? mod.default.fileTypeFromBuffer
        : undefined;

    if (detector) {
      cachedDetector = detector;
      return detector;
    }
  } catch {
    // fall back below
  }

  cachedDetector = async (buf: Buffer) => {
    const header = buf.slice(0, 5).toString('ascii');
    return header === '%PDF-' ? { mime: 'application/pdf' } : null;
  };

  return cachedDetector;
}

export const handler = createHandler(['POST'], async (event, _context, { json, requestId }) => {
  const payload = ingestSchema.safeParse(parseJsonBody<unknown>(event));

  if (!payload.success) {
    return json(400, {
      ok: false,
      error: 'Invalid ingest payload',
      details: payload.error.flatten().fieldErrors,
      requestId,
    });
  }

  const client = getS3Client();
  const head = await client.send(
    new HeadObjectCommand({
      Bucket: env.R2_BUCKET,
      Key: payload.data.sourceKey,
    })
  );

  if (typeof head.ContentLength === 'number' && head.ContentLength !== payload.data.size) {
    return json(409, {
      ok: false,
      error: 'Uploaded object size does not match expected size',
      requestId,
    });
  }

  const preview = await client.send(
    new GetObjectCommand({
      Bucket: env.R2_BUCKET,
      Key: payload.data.sourceKey,
      Range: 'bytes=0-4095',
    })
  );

  const buffer = await streamToBuffer(preview.Body);

  const fileTypeFromBuffer = await loadFileTypeDetector();
  const fileType = await fileTypeFromBuffer(buffer);

  if (!fileType || fileType.mime !== 'application/pdf') {
    return json(415, {
      ok: false,
      error: 'Uploaded object is not a valid PDF document',
      requestId,
    });
  }

  const jobId = randomUUID();

  return json(200, {
    ok: true,
    jobId,
    status: 'QUEUED',
    requestId,
  });
});
