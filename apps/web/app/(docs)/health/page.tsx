'use client';

import { useEffect, useState } from 'react';
import { getApiBase } from '../../../src/lib/api';

export default function HealthPage() {
  const [ok, setOk] = useState<boolean | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch(`${getApiBase()}/healthz`)
      .then(r => r.json())
      .then(data => setOk(Boolean(data.ok)))
      .catch(e => setError(String(e)));
  }, []);

  return (
    <main style={{ maxWidth: 720, margin: '40px auto', padding: 16 }}>
      <h1>API Health</h1>
      {ok === null && !error && <p>Checking…</p>}
      {ok && <p>OK</p>}
      {ok === false && <p>Not OK</p>}
      {error && <pre>{error}</pre>}
    </main>
  );
}
