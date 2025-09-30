'use client';
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';

type InitiateRes = { sourceKey: string; uploadId: string; partSize: number; parts: { partNumber: number; url: string }[] };
type IngestRes = { jobId: string };
type StatusRes = { job: any; downloadUrl?: string };

const API_BASE = process.env.NEXT_PUBLIC_API_URL || '/api';

function bytesFmt(n: number) {
  const u = ['B','KB','MB','GB'];
  let i = 0; let v = n;
  while (v > 1024 && i < u.length-1) { v/=1024; i++; }
  return `${v.toFixed(1)} ${u[i]}`;
}

export default function UploadPanel() {
  const [file, setFile] = useState<File | null>(null);
  const [progress, setProgress] = useState<number>(0);
  const [status, setStatus] = useState<string>('');
  const [err, setErr] = useState<string>('');
  const [jobId, setJobId] = useState<string>('');
  const [downloadUrl, setDownloadUrl] = useState<string>('');
  const pausedRef = useRef(false);
  const partsRef = useRef<{ ETag: string; PartNumber: number }[]>([]);

  const onDrop = useCallback((f: FileList | null) => {
    if (!f || !f[0]) return;
    const picked = f[0];
    if (!picked.name.toLowerCase().endswith?.('.pdf') && picked.type !== 'application/pdf') {
      setErr('Please select a PDF');
      return;
    }
    setErr('');
    setFile(picked);
  }, []);

  const upload = useCallback(async () => {
    if (!file) return;
    setStatus('Initiating upload...');
    setProgress(0);
    pausedRef.current = false;
    partsRef.current = [];

    // Optionally compute SHA-256 (skipped for speed)
    const initRes = await fetch(`${API_BASE}/initiate-upload`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ filename: file.name, size: file.size, contentType: file.type || 'application/pdf' }),
    });
    if (!initRes.ok) { setErr('Failed to initiate upload'); return; }
    const plan: InitiateRes = await initRes.json();

    const chunkSize = plan.partSize;
    let uploaded = 0;
    for (const part of plan.parts) {
      if (pausedRef.current) break;
      const start = (part.partNumber - 1) * chunkSize;
      const end = Math.min(file.size, start + chunkSize);
      const blob = file.slice(start, end);
      const put = await fetch(part.url, { method: 'PUT', body: blob });
      if (!put.ok) { setErr(`Part ${part.partNumber} failed`); return; }
      const etag = put.headers.get('ETag') || put.headers.get('etag') || '';
      partsRef.current.push({ ETag: etag, PartNumber: part.partNumber });
      uploaded = end;
      setProgress(Math.round( (uploaded / file.size) * 100 ));
    }
    if (pausedRef.current) { setStatus('Paused'); return; }

    setStatus('Finalizing & starting parse...');
    const ingest = await fetch(`${API_BASE}/ingest-pdf`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        sourceKey: plan.sourceKey,
        filename: file.name,
        size: file.size,
        uploadId: plan.uploadId,
        parts: partsRef.current,
      }),
    });
    if (!ingest.ok) { setErr('Failed to ingest PDF'); return; }
    const ing: IngestRes = await ingest.json();
    setJobId(ing.jobId);

    // start polling
    let tries = 0;
    const poll = async () => {
      if (!ing.jobId) return;
      const s = await fetch(`${API_BASE}/get-job-status?jobId=${ing.jobId}`);
      const json: StatusRes = await s.json();
      if (json.job?.status === 'DONE' && json.downloadUrl) {
        setStatus('Done');
        setDownloadUrl(json.downloadUrl);
        setProgress(100);
      } else if (json.job?.status === 'ERROR') {
        setErr(json.job?.error?.message || 'Processing failed');
      } else {
        setStatus(json.job?.status || 'PROCESSING');
        tries++;
        setTimeout(poll, Math.min(1000 + tries*200, 5000));
      }
    };
    poll();
  }, [file]);

  const pause = () => { pausedRef.current = true; };
  const resume = () => { pausedRef.current = false; upload(); };

  return (
    <div style={{ border: '1px dashed #999', padding: 24, borderRadius: 8 }}>
      <h3>Upload a PDF to extract schedules</h3>
      <input type="file" accept="application/pdf" onChange={(e)=>onDrop(e.target.files)} />
      {file && <div style={{ marginTop: 8 }}>
        <div><strong>{file.name}</strong> ({bytesFmt(file.size)})</div>
        <div style={{ height: 8, background: '#eee', borderRadius: 4, marginTop: 8 }}>
          <div style={{ width: `${progress}%`, height: 8 }} />
        </div>
        <div style={{ marginTop: 8 }}>
          <button onClick={upload} disabled={progress>0 && progress<100}>Start</button>
          <button onClick={pause} disabled={pausedRef.current || progress===0 || progress===100}>Pause</button>
          <button onClick={resume} disabled={!pausedRef.current || progress===100}>Resume</button>
        </div>
        <div style={{ marginTop: 8 }}>{status}</div>
        {err && <div style={{ color: 'red' }}>{err}</div>}
        {downloadUrl && <a href={downloadUrl}>Download Excel</a>}
      </div>}
    </div>
  );
}
