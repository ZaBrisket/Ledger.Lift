import { Handler } from "@netlify/functions";
import { getPool } from "./_database";

export const handler: Handler = async (event, context) => {
  const jobId = event.queryStringParameters?.jobId;
  if (!jobId) {
    return { statusCode: 400, body: JSON.stringify({ error: "Missing jobId" }) };
  }

  const pool = getPool();
  const result = await pool.query("SELECT name,confidence,row_count,col_count FROM job_schedules WHERE job_id=$1 ORDER BY confidence DESC", [jobId]);

  // Placeholder: Generate XLSX using a library like exceljs in production
  const csv = "Name,Confidence,Rows,Cols\n" + result.rows.map((r: any) => `${r.name},${r.confidence},${r.row_count},${r.col_count}`).join("\n");

  return {
    statusCode: 200,
    headers: { "Content-Type": "text/csv", "Content-Disposition": `attachment; filename="schedules_${jobId}.csv"` },
    body: csv,
  };
};
