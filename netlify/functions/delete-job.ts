import { Handler } from '@netlify/functions';
import { getPool } from './_database';
import { createHandler, parseJsonBody } from './_utils';

type DeletionPayload = {
  jobId?: string;
  userId?: string;
};

export const handler: Handler = createHandler(
  ['POST'],
  async (event, _context, { json, requestId }) => {
    const payload = parseJsonBody<DeletionPayload>(event);
    const jobId = payload.jobId;
    const userId = payload.userId;

    if (!jobId || !userId) {
      return json(400, {
        ok: false,
        error: 'Missing jobId or userId',
        requestId,
      });
    }

    const pool = getPool();
    const { rows } = await pool.query(
      `SELECT id, status, source_key, processed_key, export_key, bucket, deletion_manifest
       FROM jobs
       WHERE id=$1 AND user_id=$2`,
      [jobId, userId]
    );

    if (!rows.length) {
      return json(404, {
        ok: false,
        error: 'Job not found',
        requestId,
      });
    }

    const job = rows[0] as Record<string, any>;
    const bucket = job.bucket ?? 'default';

    const calculatedArtifacts = [
      job.source_key ? { type: 'incoming', key: job.source_key, bucket } : null,
      job.processed_key ? { type: 'processed', key: job.processed_key, bucket } : null,
      job.export_key ? { type: 'export', key: job.export_key, bucket } : null,
    ].filter(Boolean) as Array<{ type: string; key: string; bucket: string }>;

    let existingManifest = job.deletion_manifest;
    if (typeof existingManifest === 'string') {
      try {
        existingManifest = JSON.parse(existingManifest);
      } catch {
        existingManifest = undefined;
      }
    }

    if (existingManifest && typeof existingManifest !== 'object') {
      existingManifest = undefined;
    }

    const manifestArtifacts =
      existingManifest && typeof existingManifest === 'object' && Array.isArray(existingManifest.artifacts)
        ? existingManifest.artifacts
        : calculatedArtifacts;

    const manifest = {
      jobId,
      userId,
      status: 'PENDING',
      requestedAt: new Date().toISOString(),
      artifacts: manifestArtifacts,
    };

    await pool.query(
      `UPDATE jobs
       SET deletion_manifest = $3
       WHERE id=$1 AND user_id=$2`,
      [jobId, userId, manifest]
    );

    const status = typeof job.status === 'string' ? job.status.toLowerCase() : '';
    if (status === 'processing' || status === 'queued') {
      await pool.query('UPDATE jobs SET cancellation_requested=true WHERE id=$1', [jobId]);
    }

    return json(202, {
      ok: true,
      jobId,
      status: manifest.status,
      manifest,
      requestId,
    });
  }
);
