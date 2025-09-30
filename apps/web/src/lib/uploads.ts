export interface InitiateSingleUploadResponse {
  ok: true;
  uploadType: 'single';
  url: string;
  sourceKey: string;
  expiresIn: number;
}

export interface InitiateMultipartUploadResponse {
  ok: true;
  uploadType: 'multipart';
  uploadId: string;
  parts: Array<{ partNumber: number; url: string }>;
  sourceKey: string;
  partSize: number;
  expiresIn: number;
}

export type InitiateUploadResponse = InitiateSingleUploadResponse | InitiateMultipartUploadResponse;

export interface CompleteMultipartPayload {
  uploadId: string;
  sourceKey: string;
  parts: Array<{ partNumber: number; etag: string }>;
}

export interface IngestPayload {
  sourceKey: string;
  filename: string;
  size: number;
}

interface ApiErrorBody {
  ok?: boolean;
  error?: string;
  details?: Record<string, unknown>;
  requestId?: string;
}

export class UploadError extends Error {
  constructor(
    message: string,
    readonly options: {
      status?: number;
      requestId?: string | null;
      details?: Record<string, unknown>;
    } = {}
  ) {
    super(message);
    this.name = 'UploadError';
  }

  get status() {
    return this.options.status;
  }

  get requestId() {
    return this.options.requestId ?? undefined;
  }

  get details() {
    return this.options.details;
  }
}

const API_BASE = (process.env.NEXT_PUBLIC_API_URL ?? '').replace(/\/$/, '');

if (!API_BASE) {
  // eslint-disable-next-line no-console
  console.warn('NEXT_PUBLIC_API_URL is not defined. API requests will use relative paths.');
}

function resolveBaseUrl(): string {
  if (API_BASE) {
    return API_BASE;
  }

  if (typeof window !== 'undefined') {
    return window.location.origin;
  }

  return '';
}

function createRequestId() {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return crypto.randomUUID();
  }

  return Math.random().toString(36).slice(2);
}

async function callApi<T>(path: string, init: RequestInit): Promise<{ body: T; requestId: string | null; status: number }>
{
  const requestId = createRequestId();
  let response: Response;

  try {
    response = await fetch(`${resolveBaseUrl()}/api/${path}`, {
      ...init,
      headers: {
        'Content-Type': 'application/json',
        'X-Request-ID': requestId,
        ...(init.headers ?? {}),
      },
    });
  } catch (error) {
    if (error instanceof UploadError) {
      throw error;
    }

    throw new UploadError('Network request failed while communicating with the upload service.', {
      status: undefined,
    });
  }

  const responseRequestId = response.headers.get('x-request-id');
  const status = response.status;
  let body: ApiErrorBody | T | null = null;

  try {
    body = (await response.json()) as T;
  } catch {
    body = null;
  }

  if (!response.ok) {
    const errorBody = (body as ApiErrorBody) ?? {};
    throw mapError(status, errorBody, responseRequestId ?? requestId);
  }

  return {
    body: body as T,
    requestId: responseRequestId ?? requestId,
    status,
  };
}

function mapError(status: number, body: ApiErrorBody, requestId: string | null): UploadError {
  const baseDetails = body.details && typeof body.details === 'object' ? body.details : undefined;
  const messageFromBody = typeof body.error === 'string' ? body.error : undefined;
  const withRequestId = requestId ? `${requestId}` : null;

  const message = messageFromBody ?? createDefaultMessage(status);
  const suffix = withRequestId ? ` (request ${withRequestId})` : '';

  return new UploadError(`${message}${suffix}`, {
    status,
    requestId,
    details: baseDetails,
  });
}

function createDefaultMessage(status: number): string {
  switch (status) {
    case 400:
      return 'The upload request was invalid. Please try again.';
    case 403:
      return 'This browser is not allowed to upload documents.';
    case 404:
      return 'The upload endpoint is unavailable.';
    case 413:
      return 'The PDF is larger than the allowed limit.';
    case 415:
      return 'Only PDF files are supported right now.';
    case 429:
      return 'Too many upload attempts. Please slow down and retry.';
    case 500:
    case 502:
    case 503:
    case 504:
      return 'The upload service is temporarily unavailable.';
    default:
      return 'Upload failed due to an unexpected error.';
  }
}

export async function initiateUpload(payload: {
  filename: string;
  size: number;
  contentType: string;
  sha256: string;
  sha256Base64: string;
}): Promise<{ response: InitiateUploadResponse; requestId: string | null }>
{
  try {
    const result = await callApi<InitiateUploadResponse>('initiate-upload', {
      method: 'POST',
      body: JSON.stringify(payload),
    });

    return { response: result.body, requestId: result.requestId };
  } catch (error) {
    if (error instanceof UploadError) {
      throw error;
    }

    throw new UploadError('Failed to contact the upload service.', {});
  }
}

export async function completeMultipartUpload(payload: CompleteMultipartPayload): Promise<{ requestId: string | null }>
{
  try {
    const result = await callApi<{ ok: boolean; eTag: string | null }>('complete-multipart', {
      method: 'POST',
      body: JSON.stringify(payload),
    });

    return { requestId: result.requestId };
  } catch (error) {
    if (error instanceof UploadError) {
      throw error;
    }

    throw new UploadError('Failed to finalize multipart upload.', {});
  }
}

export async function ingestPdf(payload: IngestPayload): Promise<{ jobId: string; status: string; requestId: string | null }>
{
  try {
    const result = await callApi<{ ok: boolean; jobId: string; status: string }>('ingest-pdf', {
      method: 'POST',
      body: JSON.stringify(payload),
    });

    return { jobId: result.body.jobId, status: result.body.status, requestId: result.requestId };
  } catch (error) {
    if (error instanceof UploadError) {
      throw error;
    }

    throw new UploadError('Failed to queue ingestion for processing.', {});
  }
}
