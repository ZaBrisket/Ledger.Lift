'use client';

import { useState } from 'react';

export default function UploadSmokePage() {
  const [status, setStatus] = useState('Ready');
  const [docId, setDocId] = useState<string | null>(null);

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setStatus('Processing...');
    
    try {
      // Simulate the upload flow for E2E testing
      await new Promise(resolve => setTimeout(resolve, 1000));
      
      const mockDocId = 'smoke-test-' + Date.now();
      setDocId(mockDocId);
      setStatus('Done');
    } catch (error) {
      setStatus('Error: ' + (error as Error).message);
    }
  };

  return (
    <div style={{ padding: '2rem', maxWidth: '600px', margin: '0 auto' }}>
      <h1>Upload Smoke Test</h1>
      <p>Simple upload test page for E2E testing</p>
      
      <div style={{ marginBottom: '1rem' }}>
        <input 
          type="file" 
          accept="application/pdf"
          onChange={handleFileUpload}
          data-testid="file-input"
        />
      </div>
      
      <div data-testid="status" style={{ 
        padding: '1rem', 
        border: '1px solid #ccc', 
        borderRadius: '4px',
        backgroundColor: '#f9f9f9'
      }}>
        Status: {status}
      </div>
      
      {docId && (
        <div data-testid="success-message" style={{ 
          marginTop: '1rem',
          padding: '1rem',
          border: '1px solid #4caf50',
          borderRadius: '4px',
          backgroundColor: '#e8f5e8'
        }}>
          <h3>Success!</h3>
          <p>Document ID: <code data-testid="doc-id">{docId}</code></p>
          <button data-testid="done-button">Done</button>
        </div>
      )}
    </div>
  );
}