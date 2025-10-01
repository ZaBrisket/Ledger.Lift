import { z } from 'zod';

const booleanString = z
  .union([z.enum(['true', 'false']), z.undefined()])
  .transform((value) => value === 'true');

const normalizeOrigin = (origin: string) => origin.toLowerCase().replace(/\/$/, '');

const envSchema = z
  .object({
    NEXT_PUBLIC_API_URL: z
      .union([
        z.string().url({ message: 'NEXT_PUBLIC_API_URL must be a valid URL' }),
        z.literal(''),
      ])
      .optional()
      .default(''),
    ALLOWED_ORIGINS: z.string().min(1, 'ALLOWED_ORIGINS is required'),
    PDF_MAX_MB: z.coerce
      .number({ invalid_type_error: 'PDF_MAX_MB must be a number' })
      .positive('PDF_MAX_MB must be greater than 0'),
    NEXT_PUBLIC_PDF_MAX_MB: z
      .union([
        z.coerce
          .number({ invalid_type_error: 'NEXT_PUBLIC_PDF_MAX_MB must be a number' })
          .positive('NEXT_PUBLIC_PDF_MAX_MB must be greater than 0'),
        z.undefined(),
      ])
      .optional(),
    PRESIGN_TTL: z.coerce
      .number({ invalid_type_error: 'PRESIGN_TTL must be a number' })
      .positive('PRESIGN_TTL must be greater than 0')
      .default(900),
    REGION: z.string().min(1, 'REGION is required'),
    R2_S3_ENDPOINT: z
      .string()
      .min(1, 'R2_S3_ENDPOINT is required')
      .transform((value) => value.replace(/\/$/, '')),
    R2_BUCKET: z.string().min(1, 'R2_BUCKET is required'),
    R2_ACCESS_KEY_ID: z.string().min(1, 'R2_ACCESS_KEY_ID is required'),
    R2_SECRET_ACCESS_KEY: z.string().min(1, 'R2_SECRET_ACCESS_KEY is required'),
    R2_MULTIPART_THRESHOLD_MB: z.coerce
      .number({ invalid_type_error: 'R2_MULTIPART_THRESHOLD_MB must be a number' })
      .positive('R2_MULTIPART_THRESHOLD_MB must be greater than 0'),
    FEATURES_T1_QUEUE: booleanString,
    FEATURES_T2_OCR: booleanString,
    FEATURES_T3_AUDIT: booleanString,
    NODE_ENV: z.enum(['development', 'production'], {
      errorMap: () => ({ message: 'NODE_ENV must be development or production' }),
    }),
  })
  .superRefine((data, ctx) => {
    if (data.R2_MULTIPART_THRESHOLD_MB < 5) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: 'R2_MULTIPART_THRESHOLD_MB must be at least 5MB to satisfy S3 multipart limits',
        path: ['R2_MULTIPART_THRESHOLD_MB'],
      });
    }

    if (data.R2_MULTIPART_THRESHOLD_MB > data.PDF_MAX_MB) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: 'R2_MULTIPART_THRESHOLD_MB cannot exceed PDF_MAX_MB',
        path: ['R2_MULTIPART_THRESHOLD_MB'],
      });
    }
  });

export type Env = ReturnType<typeof loadEnv>;

export function loadEnv(customEnv: NodeJS.ProcessEnv = process.env) {
  try {
    const parsed = envSchema.parse(customEnv);

    const allowedOrigins = parsed.ALLOWED_ORIGINS.split(',')
      .map((origin) => origin.trim())
      .filter(Boolean);

    if (allowedOrigins.length === 0) {
      throw new Error('ALLOWED_ORIGINS must include at least one origin');
    }

    const megabyte = 1024 * 1024;

    return {
      NEXT_PUBLIC_API_URL: parsed.NEXT_PUBLIC_API_URL
        ? parsed.NEXT_PUBLIC_API_URL.replace(/\/$/, '')
        : '',
      ALLOWED_ORIGINS: allowedOrigins,
      ALLOWED_ORIGINS_NORMALIZED: allowedOrigins.map(normalizeOrigin),
      PDF_MAX_MB: parsed.PDF_MAX_MB,
      PDF_MAX_BYTES: parsed.PDF_MAX_MB * megabyte,
      NEXT_PUBLIC_PDF_MAX_MB: parsed.NEXT_PUBLIC_PDF_MAX_MB ?? parsed.PDF_MAX_MB,
      PRESIGN_TTL: parsed.PRESIGN_TTL,
      REGION: parsed.REGION,
      R2_S3_ENDPOINT: parsed.R2_S3_ENDPOINT.startsWith('http')
        ? parsed.R2_S3_ENDPOINT
        : `https://${parsed.R2_S3_ENDPOINT}`,
      R2_BUCKET: parsed.R2_BUCKET,
      R2_ACCESS_KEY_ID: parsed.R2_ACCESS_KEY_ID,
      R2_SECRET_ACCESS_KEY: parsed.R2_SECRET_ACCESS_KEY,
      R2_MULTIPART_THRESHOLD_MB: parsed.R2_MULTIPART_THRESHOLD_MB,
      R2_MULTIPART_THRESHOLD_BYTES: parsed.R2_MULTIPART_THRESHOLD_MB * megabyte,
      FEATURES: {
        T1_QUEUE: parsed.FEATURES_T1_QUEUE,
        T2_OCR: parsed.FEATURES_T2_OCR,
        T3_AUDIT: parsed.FEATURES_T3_AUDIT,
      },
      NODE_ENV: parsed.NODE_ENV,
    } as const;
  } catch (error) {
    if (error instanceof z.ZodError) {
      const issues = error.issues.map((issue) => `${issue.path.join('.') || 'root'}: ${issue.message}`);
      throw new Error(`Invalid environment configuration. Fix the following: ${issues.join('; ')}`);
    }

    throw error;
  }
}

export const env = loadEnv();
