import { describe, expect, it, beforeEach, vi } from 'vitest';
import { baseEnv, loadModule } from './helpers';

const s3SendMock = vi.fn();

vi.mock('@aws-sdk/client-s3', () => {
  class BaseCommand {
    constructor(public input: Record<string, unknown>) {}
  }

  class CreateMultipartUploadCommand extends BaseCommand {
    readonly __type = 'CreateMultipartUploadCommand';
  }

  class UploadPartCommand extends BaseCommand {
    readonly __type = 'UploadPartCommand';
  }

  class S3Client {
    async send(command: BaseCommand) {
      if (command instanceof CreateMultipartUploadCommand) {
        return { UploadId: 'upload-max' };
      }

      return s3SendMock(command);
    }
  }

  return { S3Client, CreateMultipartUploadCommand, UploadPartCommand };
});

const getSignedUrlMock = vi.fn(async (_client, command: any) => {
  return `https://upload.example.com/${command.input.PartNumber ?? 'single'}`;
});

vi.mock('@aws-sdk/s3-request-presigner', () => ({
  getSignedUrl: (...args: unknown[]) => getSignedUrlMock(...args),
}));

const eventBase = {
  headers: { origin: baseEnv.ALLOWED_ORIGINS },
  isBase64Encoded: false,
  path: '/api/initiate-upload',
  queryStringParameters: {},
  multiValueHeaders: {},
  multiValueQueryStringParameters: {},
};

describe('multipart limits', () => {
  beforeEach(() => {
    s3SendMock.mockReset();
    getSignedUrlMock.mockClear();
  });

  it('handles 50TB file at boundary', async () => {
    const fiftyTb = 50 * 1024 ** 4;
    const { handler } = await loadModule<typeof import('../netlify/functions/initiate-upload')>(
      '../netlify/functions/initiate-upload'
    );

    const response = await handler(
      {
        ...eventBase,
        httpMethod: 'POST',
        body: JSON.stringify({
          filename: 'huge.pdf',
          size: fiftyTb,
          contentType: 'application/pdf',
          sha256: 'c'.repeat(64),
          sha256Base64: `${'C'.repeat(43)}=`,
        }),
      } as any,
      {} as any
    );

    expect(response.statusCode).toBe(200);
    const body = JSON.parse(response.body);
    expect(body.uploadType).toBe('multipart');
    expect(body.parts).toHaveLength(10_000);
    expect(body.partSize).toBe(5 * 1024 ** 3);
  });

  it('rejects 50TB + 1 byte', async () => {
    const fiftyTbPlus = 50 * 1024 ** 4 + 1;
    const { handler } = await loadModule<typeof import('../netlify/functions/initiate-upload')>(
      '../netlify/functions/initiate-upload'
    );

    const response = await handler(
      {
        ...eventBase,
        httpMethod: 'POST',
        body: JSON.stringify({
          filename: 'too-big.pdf',
          size: fiftyTbPlus,
          contentType: 'application/pdf',
          sha256: 'd'.repeat(64),
          sha256Base64: `${'D'.repeat(43)}=`,
        }),
      } as any,
      {} as any
    );

    expect(response.statusCode).toBe(413);
    const body = JSON.parse(response.body);
    expect(body.error).toMatch(/maximum size/i);
  });
});
