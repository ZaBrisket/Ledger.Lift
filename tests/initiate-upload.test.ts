import { describe, expect, it, vi, beforeEach } from 'vitest';
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

  class PutObjectCommand extends BaseCommand {
    readonly __type = 'PutObjectCommand';
  }

  class CompleteMultipartUploadCommand extends BaseCommand {
    readonly __type = 'CompleteMultipartUploadCommand';
  }

  class GetObjectCommand extends BaseCommand {
    readonly __type = 'GetObjectCommand';
  }

  class HeadObjectCommand extends BaseCommand {
    readonly __type = 'HeadObjectCommand';
  }

  class S3Client {
    async send(command: BaseCommand) {
      return s3SendMock(command);
    }
  }

  return {
    S3Client,
    CreateMultipartUploadCommand,
    UploadPartCommand,
    PutObjectCommand,
    CompleteMultipartUploadCommand,
    GetObjectCommand,
    HeadObjectCommand,
  };
});

const getSignedUrlMock = vi.fn(async () => 'https://signed.example.com');

vi.mock('@aws-sdk/s3-request-presigner', () => ({
  getSignedUrl: (...args: unknown[]) => getSignedUrlMock(...args),
}));

const validBody = {
  filename: 'statement.pdf',
  size: 1024,
  contentType: 'application/pdf',
  sha256: 'a'.repeat(64),
  sha256Base64: 'A'.repeat(44),
};

const eventBase = {
  headers: { origin: baseEnv.ALLOWED_ORIGINS },
  isBase64Encoded: false,
  path: '/api/initiate-upload',
  queryStringParameters: {},
  multiValueHeaders: {},
  multiValueQueryStringParameters: {},
};

beforeEach(() => {
  s3SendMock.mockReset();
  getSignedUrlMock.mockClear();
});

describe('initiate-upload function', () => {
  it('rejects uploads that exceed the size limit', async () => {
    const { handler } = await loadModule<typeof import('../netlify/functions/initiate-upload')>(
      '../netlify/functions/initiate-upload'
    );

    const response = await handler(
      {
        ...eventBase,
        httpMethod: 'POST',
        body: JSON.stringify({
          ...validBody,
          size: 101 * 1024 * 1024,
        }),
      } as any,
      {} as any
    );

    expect(response.statusCode).toBe(413);
    expect(JSON.parse(response.body).error).toMatch(/maximum size/i);
  });

  it('rejects uploads with non-PDF content types', async () => {
    const { handler } = await loadModule<typeof import('../netlify/functions/initiate-upload')>(
      '../netlify/functions/initiate-upload'
    );

    const response = await handler(
      {
        ...eventBase,
        httpMethod: 'POST',
        body: JSON.stringify({
          ...validBody,
          contentType: 'application/octet-stream',
        }),
      } as any,
      {} as any
    );

    expect(response.statusCode).toBe(415);
    expect(JSON.parse(response.body).error).toMatch(/supported/i);
  });
});
