import { S3Client } from '@aws-sdk/client-s3';
import { env } from '../../src/config/env';

let client: S3Client | null = null;

export function getS3Client(): S3Client {
  if (!client) {
    client = new S3Client({
      region: env.REGION,
      endpoint: env.R2_S3_ENDPOINT,
      forcePathStyle: true,
      credentials: {
        accessKeyId: env.R2_ACCESS_KEY_ID,
        secretAccessKey: env.R2_SECRET_ACCESS_KEY,
      },
    });
  }

  return client;
}
