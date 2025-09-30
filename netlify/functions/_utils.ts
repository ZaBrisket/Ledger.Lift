import type { Handler, HandlerContext, HandlerEvent, HandlerResponse } from '@netlify/functions';
import { randomUUID } from 'crypto';
import { env } from '../../src/config/env';

const ALLOW_HEADERS = 'content-type,x-request-id,authorization,accept,accept-language,x-amz-checksum-sha256';
const ALLOW_METHODS = 'GET,POST,PUT,DELETE,OPTIONS';
const MAX_AGE_SECONDS = '600';

type HandlerResult = Omit<HandlerResponse, 'headers' | 'statusCode' | 'body'> & {
  statusCode?: number;
  headers?: Record<string, string>;
  body?: string;
};

type HandlerFn = (
  event: HandlerEvent,
  context: HandlerContext,
  utils: {
    requestId: string;
    origin: string | null;
    json: (statusCode: number, payload: unknown, headers?: Record<string, string>) => HandlerResult;
  }
) => Promise<HandlerResult>;

const normalizeOrigin = (origin: string) => origin.toLowerCase().replace(/\/$/, '');

function resolveOrigin(originValue: string | undefined): string | null {
  if (!originValue) {
    return null;
  }

  const normalized = normalizeOrigin(originValue);
  const index = env.ALLOWED_ORIGINS_NORMALIZED.indexOf(normalized);
  if (index === -1) {
    return null;
  }

  return env.ALLOWED_ORIGINS[index];
}

function baseHeaders(requestId: string, origin: string | null): Record<string, string> {
  const headers: Record<string, string> = {
    'X-Request-ID': requestId,
    Vary: 'Origin',
  };

  if (origin) {
    headers['Access-Control-Allow-Origin'] = origin;
  }

  return headers;
}

export function jsonResponse(statusCode: number, payload: unknown): HandlerResult {
  return {
    statusCode,
    body: JSON.stringify(payload),
    headers: {
      'Content-Type': 'application/json',
    },
  };
}

export function parseJsonBody<T>(event: HandlerEvent): T {
  if (!event.body) {
    throw new Error('Request body is required');
  }

  try {
    return JSON.parse(event.body) as T;
  } catch {
    throw new Error('Invalid JSON body');
  }
}

export function createHandler(allowedMethods: string[], handler: HandlerFn): Handler {
  return async (event, context) => {
    const requestId = randomUUID();
    const requestedOrigin = event.headers?.origin ?? event.headers?.Origin;
    const origin = resolveOrigin(requestedOrigin);

    if (event.httpMethod === 'OPTIONS') {
      if (requestedOrigin && !origin) {
        return {
          statusCode: 403,
          headers: {
            ...baseHeaders(requestId, null),
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ error: 'Origin not allowed', requestId }),
        };
      }

      const allowOrigin = origin ?? env.ALLOWED_ORIGINS[0] ?? '*';
      return {
        statusCode: 204,
        headers: {
          ...baseHeaders(requestId, allowOrigin),
          'Access-Control-Allow-Methods': ALLOW_METHODS,
          'Access-Control-Allow-Headers': ALLOW_HEADERS,
          'Access-Control-Max-Age': MAX_AGE_SECONDS,
        },
        body: '',
      };
    }

    if (requestedOrigin && !origin) {
      return {
        statusCode: 403,
        headers: {
          ...baseHeaders(requestId, null),
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ error: 'Origin not allowed', requestId }),
      };
    }

    if (!allowedMethods.includes(event.httpMethod)) {
      return {
        statusCode: 405,
        headers: {
          ...baseHeaders(requestId, origin),
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ error: 'Method Not Allowed', requestId }),
      };
    }

    const json = (statusCode: number, payload: unknown, headers: Record<string, string> = {}): HandlerResult => ({
      statusCode,
      body: JSON.stringify(payload),
      headers: {
        'Content-Type': 'application/json',
        ...headers,
      },
    });

    try {
      const result = await handler(event, context, { requestId, origin, json });
      return {
        statusCode: result.statusCode ?? 200,
        headers: {
          ...baseHeaders(requestId, origin),
          ...result.headers,
        },
        body: result.body ?? '',
      };
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Unknown error';
      console.error(`request ${requestId} failed: ${message}`);
      return {
        statusCode: 500,
        headers: {
          ...baseHeaders(requestId, origin),
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ error: 'Internal Server Error', requestId }),
      };
    }
  };
}
