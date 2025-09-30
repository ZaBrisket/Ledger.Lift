import { Blob } from 'buffer';
import { File, Headers } from 'undici';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { computeHashes } from '../apps/web/src/lib/hash';
import { uploadPartWithRetry } from '../apps/web/src/components/UploadPanel';

const originalFetch = global.fetch;
const originalBtoa = globalThis.btoa;

describe('client upload utilities', () => {
  beforeEach(() => {
    if (!globalThis.btoa) {
      globalThis.btoa = (input: string) => Buffer.from(input, 'binary').toString('base64');
    }
  });

  afterEach(() => {
    if (originalFetch) {
      global.fetch = originalFetch;
    } else {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      delete (global as any).fetch;
    }

    if (originalBtoa) {
      globalThis.btoa = originalBtoa;
    } else {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      delete (globalThis as any).btoa;
    }

    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('computes stable SHA-256 hashes for files', async () => {
    const file = new File(['LedgerLift'], 'ledger.pdf', { type: 'application/pdf' });
    const result = await computeHashes(file);

    expect(result.hex).toBe('e37732a6714f4679e977a09b976c91e40bd71768b25603aefed35b5d10e5d97a');
    expect(result.base64).toBe('43cypnFPRnnpd6Cbl2yR5AvXF2iyVgOu/tNbXRDl2Xo=');
  });

  it('retries uploads on transient failures and returns the final ETag', async () => {
    vi.useFakeTimers();

    const fetchMock = vi
      .fn()
      .mockRejectedValueOnce(new Error('network down'))
      .mockResolvedValueOnce({ ok: true, status: 200, headers: new Headers({ etag: '"abc123"' }) });

    global.fetch = fetchMock as unknown as typeof fetch;

    const promise = uploadPartWithRetry('https://upload.test', new Blob(['chunk']), 1, 3);

    await vi.advanceTimersByTimeAsync(1000);
    const etag = await promise;

    expect(etag).toBe('abc123');
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it('fails when storage omits the ETag header', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200, headers: new Headers() });
    global.fetch = fetchMock as unknown as typeof fetch;

    await expect(
      uploadPartWithRetry('https://upload.test', new Blob(['chunk']), 2, 2)
    ).rejects.toThrow(/Missing ETag/i);
  });
});
