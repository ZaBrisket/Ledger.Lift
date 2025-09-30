import { Handler } from '@netlify/functions';
import { z } from 'zod';
import { getJob } from '../../src/lib/jobs/repo';
import { presignGet } from '../../src/lib/storage/s3';
import { preflight, ok, error } from '../../src/lib/http/httpUtils';

const Q = z.object({ jobId: z.string().min(1) });

export const handler: Handler = async (event) => {
  if (event.httpMethod === 'OPTIONS') return preflight(event.headers?.origin);
  try {
    const { jobId } = Q.parse((event.queryStringParameters || {}));
    const job = await getJob(jobId);
    if (!job) return error(404, 'Job not found', event.headers?.origin);
    // add ephemeral download url when complete
    let downloadUrl: string | undefined;
    if (job.status === 'DONE' && job.exportKey) {
      downloadUrl = await presignGet(job.exportKey, 60 * 30);
    }
    return ok({ job, downloadUrl }, event.headers?.origin);
  } catch (e: any) {
    return error(400, e?.message || 'Bad Request', event.headers?.origin);
  }
};
