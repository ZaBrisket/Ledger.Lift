import { beforeEach, describe, expect, it, vi } from 'vitest';
import { baseEnv, loadModule } from './helpers';

const s3SendMock = vi.fn(async () => ({ ETag: 'etag-final' }));

vi.mock('@aws-sdk/client-s3', () => {
  class BaseCommand {
    constructor(public input: Record<string, unknown>) {}
  }

  class CompleteMultipartUploadCommand extends BaseCommand {
    readonly __type = 'CompleteMultipartUploadCommand';
  }

  class S3Client {
    async send(command: BaseCommand) {
      return s3SendMock(command);
    }
  }

  return { S3Client, CompleteMultipartUploadCommand };
});

const eventBase = {
  headers: { origin: baseEnv.ALLOWED_ORIGINS },
  isBase64Encoded: false,
  path: '/api/complete-multipart',
  queryStringParameters: {},
  multiValueHeaders: {},
  multiValueQueryStringParameters: {},
};

describe('complete-multipart etag normalization', () => {
  beforeEach(() => {
    s3SendMock.mockClear();
  });

  it('strips quotes from etags before sending to S3', async () => {
    const { handler } = await loadModule<typeof import('../netlify/functions/complete-multipart')>(
      '../netlify/functions/complete-multipart'
    );

    const response = await handler(
      {
        ...eventBase,
        httpMethod: 'POST',
        body: JSON.stringify({
          uploadId: 'upload-123',
          sourceKey: `uploads/${'e'.repeat(64)}/file.pdf`,
          parts: [
            { partNumber: 1, etag: '"abc123"' },
            { partNumber: 2, etag: 'plainetag' },
          ],
        }),
      } as any,
      {} as any
    );

    expect(response.statusCode).toBe(200);
    const command = s3SendMock.mock.calls[0][0];
    expect(command.input.MultipartUpload.Parts).toEqual([
      { PartNumber: 1, ETag: 'abc123' },
      { PartNumber: 2, ETag: 'plainetag' },
    ]);
  });

  it('rejects invalid source keys', async () => {
    const { handler } = await loadModule<typeof import('../netlify/functions/complete-multipart')>(
      '../netlify/functions/complete-multipart'
    );

    const response = await handler(
      {
        ...eventBase,
        httpMethod: 'POST',
        body: JSON.stringify({
          uploadId: 'upload-456',
          sourceKey: 'invalid/key.pdf',
          parts: [{ partNumber: 1, etag: 'etag' }],
        }),
      } as any,
      {} as any
    );

    expect(response.statusCode).toBe(400);
    const body = JSON.parse(response.body);
    expect(body.error).toMatch(/invalid sourcekey/i);
  });
});
