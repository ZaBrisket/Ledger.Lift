import { Handler } from "@netlify/functions";
import { getPool } from "./_database";
import { createHandler } from "./_utils";

export const handler: Handler = createHandler(async (event, context) => {
  const jobId = event.queryStringParameters?.jobId;
  const userId = event.queryStringParameters?.userId;
  if (!jobId || !userId) {
    throw { statusCode: 400, message: "Missing jobId or userId" };
  }

  const pool = getPool();
  await pool.query(
    "INSERT INTO deletion_manifests(job_id,user_id,status,artifacts) SELECT $1,$2,'PENDING',ARRAY[]::TEXT[] WHERE EXISTS(SELECT 1 FROM jobs WHERE id=$1 AND user_id=$2)",
    [jobId, userId]
  );

  await pool.query("UPDATE jobs SET cancellation_requested=true WHERE id=$1 AND status='processing'", [jobId]);

  return { message: "Deletion initiated", jobId };
});
