import { describe, expect, it } from 'vitest';
import { baseEnv, loadModule } from './helpers';

describe('CORS utilities', () => {
  const allowedOrigin = baseEnv.ALLOWED_ORIGINS;

  const buildEvent = (overrides: Partial<Record<string, unknown>> = {}) => ({
    httpMethod: 'OPTIONS',
    headers: { origin: allowedOrigin },
    body: null,
    isBase64Encoded: false,
    path: '/api/test',
    queryStringParameters: {},
    multiValueHeaders: {},
    multiValueQueryStringParameters: {},
    ...overrides,
  });

  it('returns correct headers for preflight requests', async () => {
    const { createHandler } = await loadModule<typeof import('../netlify/functions/_utils')>(
      '../netlify/functions/_utils'
    );

    const handler = createHandler(['POST'], async () => ({ statusCode: 200, body: JSON.stringify({ ok: true }) }));
    const response = await handler(buildEvent(), {} as any);

    expect(response.statusCode).toBe(204);
    expect(response.headers?.['Access-Control-Allow-Origin']).toBe(allowedOrigin);
    expect(response.headers?.['Access-Control-Allow-Methods']).toContain('POST');
    expect(response.headers?.['X-Request-ID']).toBeDefined();
  });

  it('rejects requests from disallowed origins', async () => {
    const { createHandler } = await loadModule<typeof import('../netlify/functions/_utils')>(
      '../netlify/functions/_utils'
    );

    const handler = createHandler(['POST'], async () => ({ statusCode: 200, body: JSON.stringify({ ok: true }) }));
    const response = await handler(
      buildEvent({ httpMethod: 'POST', headers: { origin: 'https://bad.test' }, body: '{}' }),
      {} as any
    );

    expect(response.statusCode).toBe(403);
    expect(response.headers?.['X-Request-ID']).toBeDefined();
  });

  it('injects request IDs on standard requests', async () => {
    const { createHandler } = await loadModule<typeof import('../netlify/functions/_utils')>(
      '../netlify/functions/_utils'
    );

    const handler = createHandler(['GET'], async () => ({
      statusCode: 200,
      body: JSON.stringify({ ok: true }),
    }));

    const response = await handler(
      buildEvent({ httpMethod: 'GET', headers: { origin: allowedOrigin } }),
      {} as any
    );

    expect(response.statusCode).toBe(200);
    expect(response.headers?.['X-Request-ID']).toBeDefined();
    expect(response.headers?.['Access-Control-Allow-Origin']).toBe(allowedOrigin);
  });
});
