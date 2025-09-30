import { vi } from 'vitest';

export const baseEnv = {
  NEXT_PUBLIC_API_URL: 'https://frontend.test',
  ALLOWED_ORIGINS: 'https://frontend.test',
  PDF_MAX_MB: '100',
  REGION: 'auto',
  R2_S3_ENDPOINT: 'https://example.r2.cloudflarestorage.com',
  R2_BUCKET: 'ledger-test',
  R2_ACCESS_KEY_ID: 'access',
  R2_SECRET_ACCESS_KEY: 'secret',
  R2_MULTIPART_THRESHOLD_MB: '50',
  PRESIGN_TTL: '900',
  FEATURES_T1_QUEUE: 'false',
  FEATURES_T2_OCR: 'false',
  FEATURES_T3_AUDIT: 'false',
  NODE_ENV: 'development',
  NEXT_PUBLIC_PDF_MAX_MB: '100',
} as const;

type EnvOverrides = Partial<Record<keyof typeof baseEnv, string | undefined>>;

export async function loadModule<T>(path: string, overrides: EnvOverrides = {}): Promise<T> {
  vi.resetModules();
  const nextEnv: NodeJS.ProcessEnv = { ...baseEnv } as unknown as NodeJS.ProcessEnv;

  for (const key of Object.keys(overrides) as Array<keyof typeof baseEnv>) {
    const value = overrides[key];
    if (typeof value === 'undefined') {
      delete (nextEnv as Record<string, string>)[key as string];
    } else {
      (nextEnv as Record<string, string>)[key as string] = value;
    }
  }

  process.env = nextEnv;
  const module = (await import(path)) as T;
  return module;
}
