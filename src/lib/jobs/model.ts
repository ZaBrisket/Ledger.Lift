export type JobStatus = 'QUEUED' | 'PROCESSING' | 'DONE' | 'ERROR' | 'CANCELLED';

export interface JobDoc {
  jobId: string;
  status: JobStatus;
  createdAt: string;
  updatedAt: string;
  sourceKey: string;
  exportKey?: string;
  filename?: string;
  size?: number;
  progress?: { step: string; pct: number }[];
  error?: { code: string; message: string; detail?: any };
  logs?: { t: string; lvl: 'info'|'warn'|'error'; msg: string; kid?: string }[];
  corr?: string; // correlation id
}

export const paths = {
  job: (id: string) => `jobs/${id}.json`,
};
