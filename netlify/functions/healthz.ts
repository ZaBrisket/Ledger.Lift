import { createHandler } from './_utils';

export const handler = createHandler(['GET'], async (_event, _context, { json, requestId }) => {
  return json(200, {
    ok: true,
    service: 'ledger-lift',
    version: process.env.npm_package_version ?? 'dev',
    time: new Date().toISOString(),
    requestId,
  });
});
