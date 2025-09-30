import {
  S3Client,
  CreateMultipartUploadCommand,
  UploadPartCommand,
  CompleteMultipartUploadCommand,
  AbortMultipartUploadCommand,
  GetObjectCommand,
  PutObjectCommand,
  HeadObjectCommand,
} from '@aws-sdk/client-s3';
import { getSignedUrl } from '@aws-sdk/s3-request-presigner';
import { env } from '../../config/env';

export type MultipartPlan = {
  uploadId: string;
  key: string;
  partSize: number;
  parts: { partNumber: number; url: string }[];
};

let client: S3Client | null = null;

export function s3() {
  if (client) return client;
  const base = {
    region: env.R2_REGION || 'auto',
    credentials: {
      accessKeyId: env.R2_ACCESS_KEY_ID,
      secretAccessKey: env.R2_SECRET_ACCESS_KEY,
    },
  };
  client = new S3Client(
    env.R2_S3_ENDPOINT
      ? { ...base, endpoint: env.R2_S3_ENDPOINT, forcePathStyle: true }
      : base as any
  );
  return client!;
}

export async function planMultipartUpload(key: string, sizeBytes: number, contentType: string, partSize = 5 * 1024 * 1024): Promise<MultipartPlan> {
  // S3 minimum part size is 5MB except last part.
  if (partSize < 5 * 1024 * 1024) partSize = 5 * 1024 * 1024;
  const create = await s3().send(new CreateMultipartUploadCommand({
    Bucket: env.R2_BUCKET,
    Key: key,
    ContentType: contentType,
  }));

  const uploadId = create.UploadId!;
  const partCount = Math.ceil(sizeBytes / partSize);
  const parts: { partNumber: number; url: string }[] = [];
  for (let i = 1; i <= partCount; i++) {
    const url = await getSignedUrl(s3(), new UploadPartCommand({
      Bucket: env.R2_BUCKET,
      Key: key,
      PartNumber: i,
      UploadId: uploadId,
    }), { expiresIn: 60 * 30 });
    parts.push({ partNumber: i, url });
  }
  return { uploadId, key, partSize, parts };
}

export async function completeMultipartUpload(key: string, uploadId: string, etags: { ETag: string; PartNumber: number }[]) {
  // ETag must be quoted strings
  const Parts = etags.map(p => ({ ETag: p.ETag.replace(/^(?!\").+/, m => `"${m}"`).replace(/(^"?)(.*?)("?$)/, '"$2"'), PartNumber: p.PartNumber }));
  const out = await s3().send(new CompleteMultipartUploadCommand({
    Bucket: env.R2_BUCKET,
    Key: key,
    UploadId: uploadId,
    MultipartUpload: { Parts },
  }));
  return out;
}

export async function abortMultipartUpload(key: string, uploadId: string) {
  await s3().send(new AbortMultipartUploadCommand({ Bucket: env.R2_BUCKET, Key: key, UploadId: uploadId }));
}

export async function putJson(key: string, data: any) {
  await s3().send(new PutObjectCommand({
    Bucket: env.R2_BUCKET,
    Key: key,
    Body: Buffer.from(JSON.stringify(data)),
    ContentType: 'application/json; charset=utf-8',
  }));
}

export async function getJson<T>(key: string): Promise<T | null> {
  try {
    const res = await s3().send(new GetObjectCommand({ Bucket: env.R2_BUCKET, Key: key }));
    // @ts-ignore
    const buf = await res.Body?.transformToByteArray?.();
    if (!buf) return null;
    return JSON.parse(Buffer.from(buf).toString('utf-8')) as T;
  } catch (e: any) {
    if (e?.name === 'NoSuchKey') return null;
    throw e;
  }
}

export async function head(key: string) {
  return await s3().send(new HeadObjectCommand({ Bucket: env.R2_BUCKET, Key: key }));
}

export async function getObjectBytes(key: string): Promise<Uint8Array> {
  const res = await s3().send(new GetObjectCommand({ Bucket: env.R2_BUCKET, Key: key }));
  // @ts-ignore
  const buf = await res.Body?.transformToByteArray?.();
  return new Uint8Array(buf);
}

export async function presignGet(key: string, expiresInSeconds = 60 * 15) {
  return await getSignedUrl(s3(), new GetObjectCommand({ Bucket: env.R2_BUCKET, Key: key }), { expiresIn: expiresInSeconds });
}
