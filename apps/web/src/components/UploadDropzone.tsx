'use client';

import React, { useRef, useState } from 'react';
import { presignUpload, registerDocument } from '../lib/api';

type Props = { 
  onStatusChange?: (s: string) => void;
  onDocumentRegistered?: (docId: string) => void;
};

export default function UploadDropzone({ onStatusChange, onDocumentRegistered }: Props) {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [busy, setBusy] = useState(false);

  async function onChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setBusy(true);
    onStatusChange?.('Presigning…');
    try {
      const presigned = await presignUpload(file.name, file.type || 'application/pdf');
      onStatusChange?.('Uploading…');
      const put = await fetch(presigned.url, { method: 'PUT', body: file, headers: { 'Content-Type': file.type || 'application/pdf' } });
      if (!put.ok) throw new Error(`PUT failed: ${put.status}`);

      onStatusChange?.('Registering…');
      const document = await registerDocument({ s3_key: presigned.key, original_filename: file.name });
      onDocumentRegistered?.(document.id);
      onStatusChange?.('Done');
    } catch (e: any) {
      onStatusChange?.(`Error: ${e.message || e}`);
    } finally {
      setBusy(false);
      if (inputRef.current) inputRef.current.value = '';
    }
  }

  return (
    <div>
      <input
        ref={inputRef}
        type="file"
        accept="application/pdf"
        onChange={onChange}
        disabled={busy}
      />
    </div>
  );
}
