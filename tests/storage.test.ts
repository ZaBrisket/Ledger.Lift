import { beforeEach, describe, expect, it, vi } from 'vitest';
import { loadModule } from './helpers';

const clientCtor = vi.fn();

vi.mock('@aws-sdk/client-s3', () => ({
  S3Client: vi.fn((options: Record<string, unknown>) => {
    clientCtor(options);
    return { send: vi.fn() };
  }),
}));

describe('getS3Client', () => {
  beforeEach(() => {
    clientCtor.mockClear();
  });

  it('disables path-style addressing for Cloudflare R2 endpoints', async () => {
    const { getS3Client } = await loadModule<typeof import('../netlify/functions/_storage')>(
      '../netlify/functions/_storage',
      {
        R2_S3_ENDPOINT: 'https://accountid.r2.cloudflarestorage.com',
      }
    );

    getS3Client();

    expect(clientCtor).toHaveBeenCalledTimes(1);
    expect(clientCtor).toHaveBeenCalledWith(
      expect.objectContaining({ forcePathStyle: false })
    );
  });

  it('retains path-style addressing for non-R2 endpoints', async () => {
    const { getS3Client } = await loadModule<typeof import('../netlify/functions/_storage')>(
      '../netlify/functions/_storage',
      {
        R2_S3_ENDPOINT: 'http://localhost:9000',
      }
    );

    getS3Client();

    expect(clientCtor).toHaveBeenCalledTimes(1);
    expect(clientCtor).toHaveBeenCalledWith(
      expect.objectContaining({ forcePathStyle: true })
    );
  });
});
