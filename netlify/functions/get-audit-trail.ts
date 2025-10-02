import { Handler } from "@netlify/functions";
import { getPool } from "./_database";
import { createHandler } from "./_utils";

export const handler: Handler = createHandler(async (event, context) => {
  const jobId = event.queryStringParameters?.jobId;
  if (!jobId) {
    throw { statusCode: 400, message: "Missing jobId parameter" };
  }

  const pool = getPool();
  const result = await pool.query(
    "SELECT id,job_id,event_type,user_id,ip_address,trace_id,metadata,created_at FROM audit_events WHERE job_id=$1 ORDER BY created_at DESC LIMIT 100",
    [jobId]
  );

  return { events: result.rows };
});
