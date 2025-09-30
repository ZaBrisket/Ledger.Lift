import { Readable } from 'node:stream';
import { beforeEach, describe, expect, it, vi } from 'vitest';
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

const getSignedUrlMock = vi.fn();

vi.mock('@aws-sdk/s3-request-presigner', () => ({
  getSignedUrl: (...args: unknown[]) => getSignedUrlMock(...args),
}));

const eventBase = {
  headers: { origin: baseEnv.ALLOWED_ORIGINS },
  isBase64Encoded: false,
  path: '/api',
  queryStringParameters: {},
  multiValueHeaders: {},
  multiValueQueryStringParameters: {},
};

beforeEach(() => {
  s3SendMock.mockReset();
  getSignedUrlMock.mockReset();
});

describe('multipart workflow', () => {
  it('provides URLs, completes upload, and queues ingestion', async () => {
    const fileSize = 60 * 1024 * 1024; // trigger multipart path

    s3SendMock.mockImplementation(async (command: any) => {
      switch (command.__type) {
        case 'CreateMultipartUploadCommand':
          return { UploadId: 'upload-abc' };
        case 'CompleteMultipartUploadCommand':
          return { ETag: '"etag-final"' };
        case 'HeadObjectCommand':
          return { ContentLength: fileSize };
        case 'GetObjectCommand':
          return { Body: Readable.from([Buffer.from('%PDF-1.7\n%âãÏÓ\n')]) };
        default:
          return {};
      }
    });

    getSignedUrlMock.mockImplementation(async (_client: unknown, command: any) => {
      if (command.__type === 'UploadPartCommand') {
        return `https://upload.test/${command.input.PartNumber}`;
      }

      return 'https://upload.test/single';
    });

    const { handler: initiate } = await loadModule<typeof import('../netlify/functions/initiate-upload')>(
      '../netlify/functions/initiate-upload'
    );
    const { handler: complete } = await loadModule<typeof import('../netlify/functions/complete-multipart')>(
      '../netlify/functions/complete-multipart'
    );
    const { handler: ingest } = await loadModule<typeof import('../netlify/functions/ingest-pdf')>(
      '../netlify/functions/ingest-pdf'
    );

    const initiateResponse = await initiate(
      {
        ...eventBase,
        httpMethod: 'POST',
        body: JSON.stringify({
          filename: 'report.pdf',
          size: fileSize,
          contentType: 'application/pdf',
          sha256: 'b'.repeat(64),
          sha256Base64: `${'B'.repeat(43)}=`,
        }),
      } as any,
      {} as any
    );

    expect(initiateResponse.statusCode).toBe(200);
    const initiateBody = JSON.parse(initiateResponse.body);
    expect(initiateBody.uploadType).toBe('multipart');
    expect(initiateBody.parts.length).toBeGreaterThan(0);

    const completeResponse = await complete(
      {
        ...eventBase,
        httpMethod: 'POST',
        body: JSON.stringify({
          uploadId: initiateBody.uploadId,
          sourceKey: initiateBody.sourceKey,
          parts: initiateBody.parts.map((part: any) => ({
            partNumber: part.partNumber,
            etag: `"etag-${part.partNumber}"`,
          })),
        }),
      } as any,
      {} as any
    );

    expect(completeResponse.statusCode).toBe(200);
    const completeBody = JSON.parse(completeResponse.body);
    expect(completeBody.ok).toBe(true);

    const ingestResponse = await ingest(
      {
        ...eventBase,
        httpMethod: 'POST',
        body: JSON.stringify({
          sourceKey: initiateBody.sourceKey,
          filename: 'report.pdf',
          size: fileSize,
        }),
      } as any,
      {} as any
    );

    expect(ingestResponse.statusCode).toBe(200);
    const ingestBody = JSON.parse(ingestResponse.body);
    expect(ingestBody.status).toBe('QUEUED');
    expect(ingestBody.jobId).toBeDefined();
  });
});
