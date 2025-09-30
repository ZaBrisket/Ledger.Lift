import { createHandler } from './_utils';

export const handler = createHandler(['GET'], async (event, _context, { json, requestId }) => {
  const jobId = event.queryStringParameters?.jobId;

  if (!jobId) {
    return json(400, {
      ok: false,
      error: 'jobId is required',
      requestId,
    });
  }

  return json(200, {
    ok: true,
    jobId,
    status: 'QUEUED',
    requestId,
  });
});
