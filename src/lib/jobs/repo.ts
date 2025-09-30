import { JobDoc, paths } from './model';
import { putJson, getJson } from '../storage/s3';

export async function createJob(doc: JobDoc) {
  await putJson(paths.job(doc.jobId), doc);
  return doc;
}

export async function getJob(jobId: string) {
  return await getJson<JobDoc>(paths.job(jobId));
}

export async function updateJob(jobId: string, patch: Partial<JobDoc>) {
  const cur = (await getJson<JobDoc>(paths.job(jobId))) || ({} as JobDoc);
  const next: JobDoc = { ...cur, ...patch, updatedAt: new Date().toISOString() };
  await putJson(paths.job(jobId), next);
  return next;
}

export async function log(jobId: string, lvl: 'info'|'warn'|'error', msg: string, kid?: string) {
  const cur = await getJson<JobDoc>(paths.job(jobId));
  const logs = cur?.logs || [];
  logs.push({ t: new Date().toISOString(), lvl, msg, kid });
  await updateJob(jobId, { logs });
}
