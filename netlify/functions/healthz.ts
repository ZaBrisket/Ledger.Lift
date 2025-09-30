import { Handler } from '@netlify/functions';
import { preflight, ok } from '../../src/lib/http/httpUtils';

export const handler: Handler = async (event) => {
  if (event.httpMethod === 'OPTIONS') return preflight(event.headers?.origin);
  return ok({ status: 'ok', version: 'pdf-to-excel-schedules-v1', time: new Date().toISOString() }, event.headers?.origin);
};
