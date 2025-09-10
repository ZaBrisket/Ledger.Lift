'use client';

import UploadDropzone from '../../../src/components/UploadDropzone';
import StatusCard from '../../../src/components/StatusCard';
import { useState } from 'react';
import { getExportUrl } from '../../../src/lib/api';
import Link from 'next/link';

export default function UploadSmokePage() {
  const [status, setStatus] = useState<string>('Idle');
  const [documentId, setDocumentId] = useState<string | null>(null);

  return (
    <main style={{ maxWidth: 720, margin: '40px auto', padding: 16 }}>
      <h1>Ledger Lift - E2E Test Page</h1>
      <p>This page is designed for automated testing. Upload a PDF to test the complete flow.</p>
      
      <UploadDropzone 
        onStatusChange={setStatus} 
        onDocumentRegistered={setDocumentId}
      />
      
      <div style={{ marginTop: 24 }}>
        <StatusCard status={status} />
      </div>
      
      {documentId && status === 'Done' && (
        <div style={{ marginTop: 24, padding: 16, border: '1px solid #ccc', borderRadius: 8 }}>
          <h3>Document Processed Successfully!</h3>
          <p>Document ID: {documentId}</p>
          <div style={{ display: 'flex', gap: '8px', marginTop: 8 }}>
            <a 
              href={getExportUrl(documentId)}
              download={`document_${documentId}_export.xlsx`}
              style={{
                display: 'inline-block',
                padding: '8px 16px',
                backgroundColor: '#007bff',
                color: 'white',
                textDecoration: 'none',
                borderRadius: 4
              }}
            >
              Download Excel Export
            </a>
            <Link 
              href={`/review/${documentId}`}
              style={{
                display: 'inline-block',
                padding: '8px 16px',
                backgroundColor: '#28a745',
                color: 'white',
                textDecoration: 'none',
                borderRadius: 4
              }}
            >
              Review & Edit Data
            </Link>
          </div>
        </div>
      )}
      
      {/* Test data for E2E */}
      <div style={{ marginTop: 24, padding: 16, backgroundColor: '#f8f9fa', borderRadius: 8 }}>
        <h4>Test Instructions:</h4>
        <ol>
          <li>Upload the sample PDF file</li>
          <li>Wait for "Done" status</li>
          <li>Verify document ID is displayed</li>
          <li>Test download and review links</li>
        </ol>
      </div>
    </main>
  );
}