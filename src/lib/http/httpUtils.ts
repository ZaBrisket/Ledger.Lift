import { env } from '../../config/env';

export function getAllowedOrigins(): string[] {
  return env.ALLOWED_ORIGINS.split(',').map((s) => s.trim()).filter(Boolean);
}

export function corsHeaders(origin?: string): Record<string, string> {
  const headers: Record<string, string> = {
    'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type, Authorization, x-amz-*, x-amz-checksum-sha256, x-correlation-id',
    'Access-Control-Allow-Credentials': 'false',
    'Vary': 'Origin',
  };
  const allowed = getAllowedOrigins();
  if (origin && allowed.includes(origin)) {
    headers['Access-Control-Allow-Origin'] = origin;
  } else {
    // Default to production site to be safe
    headers['Access-Control-Allow-Origin'] = allowed[0] || '*';
  }
  return headers;
}

export function ok(body: any, origin?: string, statusCode = 200) {
  return {
    statusCode,
    headers: { 'Content-Type': 'application/json; charset=utf-8', ...corsHeaders(origin) },
    body: JSON.stringify(body),
  };
}

export function error(statusCode: number, message: string, origin?: string, extra?: Record<string, any>) {
  return {
    statusCode,
    headers: { 'Content-Type': 'application/json; charset=utf-8', ...corsHeaders(origin) },
    body: JSON.stringify({ error: message, ...(extra || {}) }),
  };
}

export function preflight(origin?: string) {
  return {
    statusCode: 204,
    headers: { ...corsHeaders(origin) },
    body: '',
  };
}

export function correlationIdFrom(event: any): string {
  return event?.headers?.['x-correlation-id'] || event?.headers?.['X-Correlation-Id'] || cryptoRandomId();
}

export function cryptoRandomId(): string {
  // lightweight random id for correlation
  const r = Math.random().toString(16).slice(2) + Date.now().toString(16);
  return `corr_${r}`;
}
