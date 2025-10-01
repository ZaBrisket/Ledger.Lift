import { S3Client } from '@aws-sdk/client-s3';
import { env } from '../../src/config/env';

let client: S3Client | null = null;

function shouldForcePathStyle(endpoint: string): boolean {
  try {
    const url = new URL(endpoint);
    const host = url.hostname.toLowerCase();

    // Cloudflare R2 requires virtual-hosted style requests. Enabling path-style
    // addressing against an R2 endpoint produces presigned URLs that omit the
    // bucket prefix in the hostname, which in turn causes signature mismatch
    // errors (HTTP 403/503) when the browser attempts to upload the file.
    //
    // Local MinIO and similar S3-compatible services continue to rely on
    // path-style URLs, so only disable it when we detect an R2 hostname.
    if (host.endsWith('.r2.cloudflarestorage.com')) {
      return false;
    }

    return true;
  } catch {
    // Fall back to the previous behaviour if the endpoint cannot be parsed.
    return true;
  }
}

export function getS3Client(): S3Client {
  if (!client) {
    client = new S3Client({
      region: env.REGION,
      endpoint: env.R2_S3_ENDPOINT,
      forcePathStyle: shouldForcePathStyle(env.R2_S3_ENDPOINT),
      credentials: {
        accessKeyId: env.R2_ACCESS_KEY_ID,
        secretAccessKey: env.R2_SECRET_ACCESS_KEY,
      },
    });
  }

  return client;
}
