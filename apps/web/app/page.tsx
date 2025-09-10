'use client';

import UploadDropzone from '../src/components/UploadDropzone';
import StatusCard from '../src/components/StatusCard';
import { useState } from 'react';

export default function HomePage() {
  const [status, setStatus] = useState<string>('Idle');

  return (
    <main style={{ maxWidth: 720, margin: '40px auto', padding: 16 }}>
      <h1>Ledger Lift</h1>
      <p>Upload a PDF to get a pre‑signed URL and register the document.</p>
      <UploadDropzone onStatusChange={setStatus} />
      <div style={{ marginTop: 24 }}>
        <StatusCard status={status} />
      </div>
    </main>
  );
}
