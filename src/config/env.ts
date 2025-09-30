import { z } from 'zod';

const boolish = z.union([z.boolean(), z.string()]).transform((v) => {
  if (typeof v === 'boolean') return v;
  const s = v.toLowerCase().trim();
  return s === '1' || s === 'true' || s === 'yes';
});

export const EnvSchema = z.object({
  R2_S3_ENDPOINT: z.string().optional(),
  R2_ACCESS_KEY_ID: z.string().min(1, 'R2_ACCESS_KEY_ID is required'),
  R2_SECRET_ACCESS_KEY: z.string().min(1, 'R2_SECRET_ACCESS_KEY is required'),
  R2_REGION: z.string().default('auto'),
  R2_BUCKET: z.string().min(1, 'R2_BUCKET is required'),

  PDF_MAX_MB: z.preprocess((v) => Number(v), z.number().int().positive().max(2000)).default(100),
  OCR_ENABLED: boolish.default(false),
  SCALE: z.preprocess((v) => Number(v), z.number().int().min(1).max(10)).default(5),

  NODE_ENV: z.enum(['development', 'test', 'production']).default('development'),
  ALLOWED_ORIGINS: z.string().default('https://ledgerlift1.netlify.app,http://localhost:3000'),
});

export type Env = z.infer<typeof EnvSchema>;

export function loadEnv(): Env {
  const parsed = EnvSchema.safeParse(process.env);
  if (!parsed.success) {
    const messages = parsed.error.errors.map((e) => `${e.path.join('.')}: ${e.message}`).join('; ');
    throw new Error(`Environment validation failed: ${messages}`);
  }
  return parsed.data;
}

export const env = loadEnv();
