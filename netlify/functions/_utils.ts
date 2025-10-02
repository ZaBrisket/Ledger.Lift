import { randomUUID } from 'crypto';
import {
  Handler,
  HandlerContext,
  HandlerEvent,
  HandlerResponse,
} from '@netlify/functions';

type HttpMethod =
  | 'GET'
  | 'HEAD'
  | 'POST'
  | 'PUT'
  | 'PATCH'
  | 'DELETE'
  | 'OPTIONS';

type HandlerUtilities = {
  json: (statusCode: number, body: unknown, headers?: Record<string, string>) => HandlerResponse;
  text: (statusCode: number, body: string, headers?: Record<string, string>) => HandlerResponse;
  requestId: string;
};

type WrappedHandler = (
  event: HandlerEvent,
  context: HandlerContext,
  utils: HandlerUtilities
) => Promise<HandlerResponse | Record<string, unknown> | string | void>;

function createUtilities(requestId: string): HandlerUtilities {
  return {
    json(statusCode, body, headers = {}) {
      return {
        statusCode,
        headers: { 'Content-Type': 'application/json', ...headers },
        body: JSON.stringify(body ?? {}),
      };
    },
    text(statusCode, body, headers = {}) {
      return {
        statusCode,
        headers: { 'Content-Type': 'text/plain', ...headers },
        body,
      };
    },
    requestId,
  };
}

function normaliseMethods(methods: HttpMethod[] | undefined): string[] | undefined {
  return methods?.map((method) => method.toUpperCase());
}

function buildErrorResponse(
  err: unknown,
  utils: HandlerUtilities
): HandlerResponse {
  const error = err as { statusCode?: number; message?: string; body?: string } | undefined;
  const statusCode = error?.statusCode && Number.isInteger(error.statusCode)
    ? error.statusCode
    : 500;

  if (error?.body) {
    return {
      statusCode,
      headers: { 'Content-Type': 'application/json' },
      body: error.body,
    };
  }

  const message = error?.message ?? 'Internal Server Error';
  return utils.json(statusCode, { ok: false, error: message, requestId: utils.requestId });
}

function normaliseResult(
  result: HandlerResponse | Record<string, unknown> | string | void,
  utils: HandlerUtilities
): HandlerResponse {
  if (result && typeof result === 'object' && 'statusCode' in result) {
    return result as HandlerResponse;
  }

  if (typeof result === 'string') {
    return utils.text(200, result);
  }

  const payload =
    result && typeof result === 'object' ? result : {};

  return utils.json(200, payload);
}

export function createHandler(handler: WrappedHandler): Handler;
export function createHandler(methods: HttpMethod[], handler: WrappedHandler): Handler;
export function createHandler(
  methodsOrHandler: HttpMethod[] | WrappedHandler,
  maybeHandler?: WrappedHandler
): Handler {
  const methods = Array.isArray(methodsOrHandler)
    ? normaliseMethods(methodsOrHandler)
    : undefined;
  const handler = (Array.isArray(methodsOrHandler)
    ? maybeHandler
    : methodsOrHandler) as WrappedHandler;

  if (!handler) {
    throw new Error('createHandler requires a handler function');
  }

  return async (event, context) => {
    const requestId =
      event.headers?.['x-request-id'] ||
      event.headers?.['X-Request-Id'] ||
      context.awsRequestId ||
      randomUUID();
    const utils = createUtilities(requestId);

    if (
      methods &&
      event.httpMethod &&
      !methods.includes(event.httpMethod.toUpperCase())
    ) {
      return utils.json(
        405,
        {
          ok: false,
          error: `Method ${event.httpMethod} not allowed`,
          requestId,
        },
        { Allow: methods.join(', ') }
      );
    }

    try {
      const result = await handler(event, context, utils);
      return normaliseResult(result, utils);
    } catch (err) {
      return buildErrorResponse(err, utils);
    }
  };
}

export function parseJsonBody<T>(event: HandlerEvent): T {
  if (!event.body) {
    return {} as T;
  }

  const raw = event.isBase64Encoded
    ? Buffer.from(event.body, 'base64').toString('utf8')
    : event.body;

  if (!raw.trim()) {
    return {} as T;
  }

  try {
    return JSON.parse(raw) as T;
  } catch (error) {
    const err = new Error('Invalid JSON body');
    (err as any).statusCode = 400;
    throw err;
  }
}

export function binaryResponse(data: Buffer, contentType: string): HandlerResponse {
  return {
    statusCode: 200,
    headers: { 'Content-Type': contentType },
    body: data.toString('base64'),
    isBase64Encoded: true,
  };
}

export type { HandlerUtilities };
