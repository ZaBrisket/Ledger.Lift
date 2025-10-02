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
    "SELECT id,job_id,name,confidence,row_count,col_count,created_at FROM job_schedules WHERE job_id=$1 ORDER BY confidence DESC",
    [jobId]
  );

  return { schedules: result.rows };
});
