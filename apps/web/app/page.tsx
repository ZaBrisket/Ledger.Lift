'use client';

import UploadDropzone from '../src/components/UploadDropzone';
import StatusCard from '../src/components/StatusCard';
import { useState } from 'react';
import { getExportUrl } from '../src/lib/api';

export default function HomePage() {
  const [status, setStatus] = useState<string>('Idle');
  const [documentId, setDocumentId] = useState<string | null>(null);

  return (
    <main style={{ maxWidth: 720, margin: '40px auto', padding: 16 }}>
      <h1>Ledger Lift</h1>
      <p>Upload a PDF to get a pre‑signed URL and register the document.</p>
      <UploadDropzone 
        onStatusChange={setStatus} 
        onDocumentRegistered={setDocumentId}
      />
      <div style={{ marginTop: 24 }}>
        <StatusCard status={status} />
        {documentId && (
          <div style={{ marginTop: 16, padding: 16, border: '1px solid #ddd', borderRadius: 8 }}>
            <h3>Document Registered Successfully!</h3>
            <p>Document ID: <code>{documentId}</code></p>
            <div style={{ marginTop: 8 }}>
              <a 
                href={getExportUrl(documentId)}
                download
                style={{
                  display: 'inline-block',
                  marginRight: 12,
                  padding: '8px 16px',
                  backgroundColor: '#0070f3',
                  color: 'white',
                  textDecoration: 'none',
                  borderRadius: 4,
                  fontSize: 14
                }}
              >
                Download Excel
              </a>
              <a 
                href={`/review/${documentId}`}
                style={{
                  display: 'inline-block',
                  padding: '8px 16px',
                  backgroundColor: '#28a745',
                  color: 'white',
                  textDecoration: 'none',
                  borderRadius: 4,
                  fontSize: 14
                }}
              >
                Review & Edit
              </a>
            </div>
          </div>
        )}
      </div>
    </main>
  );
}
