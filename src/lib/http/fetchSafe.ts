import { setTimeout as delay } from 'node:timers/promises';
import { env } from '../../config/env';

export type FetchSafeOptions = RequestInit & {
  timeoutMs?: number;
  retries?: number;
  retryDelayMs?: number;
  correlationId?: string;
};

const DEFAULT_TIMEOUT = 15000;
const DEFAULT_RETRIES = 2;
const DEFAULT_RETRY_DELAY = 300;

export async function fetchSafe(url: string, opts: FetchSafeOptions = {}) {
  const {
    timeoutMs = DEFAULT_TIMEOUT,
    retries = DEFAULT_RETRIES,
    retryDelayMs = DEFAULT_RETRY_DELAY,
    correlationId,
    headers,
    ...rest
  } = opts;

  const controller = new AbortController();
  const id = setTimeout(() => controller.abort(), timeoutMs);
  const hdrs = new Headers(headers || {});
  if (correlationId) hdrs.set('x-correlation-id', correlationId);

  for (let attempt = 0; attempt <= retries; attempt++) {
    try {
      const res = await fetch(url, { ...rest, headers: hdrs, signal: controller.signal } as RequestInit);
      clearTimeout(id);
      return res;
    } catch (err) {
      if (attempt === retries) throw err;
      await delay(retryDelayMs * Math.pow(2, attempt));
    }
  }
}
