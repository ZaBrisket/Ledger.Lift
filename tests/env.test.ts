import { describe, expect, it } from 'vitest';
import { baseEnv, loadModule } from './helpers';

describe('environment configuration', () => {
  it('parses valid environment variables', async () => {
    const { loadEnv } = await loadModule<typeof import('../src/config/env')>('../src/config/env');
    const env = loadEnv();

    expect(env.NEXT_PUBLIC_API_URL).toBe(baseEnv.NEXT_PUBLIC_API_URL);
    expect(env.ALLOWED_ORIGINS).toEqual(['https://frontend.test']);
    expect(env.ALLOWED_ORIGINS_NORMALIZED).toEqual(['https://frontend.test']);
    expect(env.PDF_MAX_BYTES).toBe(100 * 1024 * 1024);
    expect(env.R2_MULTIPART_THRESHOLD_BYTES).toBe(50 * 1024 * 1024);
    expect(env.NEXT_PUBLIC_PDF_MAX_MB).toBe(100);
    expect(env.PRESIGN_TTL).toBe(900);
  });

  it('allows missing NEXT_PUBLIC_API_URL', async () => {
    const module = await loadModule<typeof import('../src/config/env')>(
      '../src/config/env',
      { NEXT_PUBLIC_API_URL: undefined }
    );

    const env = module.loadEnv();
    expect(env.NEXT_PUBLIC_API_URL).toBe('');
  });

  it('defaults NEXT_PUBLIC_PDF_MAX_MB to PDF_MAX_MB when omitted', async () => {
    const module = await loadModule<typeof import('../src/config/env')>(
      '../src/config/env',
      { NEXT_PUBLIC_PDF_MAX_MB: undefined }
    );

    const env = module.loadEnv();
    expect(env.NEXT_PUBLIC_PDF_MAX_MB).toBe(env.PDF_MAX_MB);
  });

  it('fails fast when allowed origins are missing', async () => {
    await expect(
      loadModule('../src/config/env', { ALLOWED_ORIGINS: '' })
    ).rejects.toThrowError(/ALLOWED_ORIGINS/);
  });

  it('rejects multipart thresholds that exceed the PDF max', async () => {
    await expect(
      loadModule('../src/config/env', { R2_MULTIPART_THRESHOLD_MB: '150' })
    ).rejects.toThrowError(/R2_MULTIPART_THRESHOLD_MB/);
  });
});
