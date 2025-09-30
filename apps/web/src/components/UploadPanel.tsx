'use client';

import { useCallback, useMemo, useState } from 'react';
import Dropzone, { FileRejection } from 'react-dropzone';
import {
  UploadError,
  completeMultipartUpload,
  ingestPdf,
  initiateUpload,
  type InitiateMultipartUploadResponse,
  type InitiateSingleUploadResponse,
} from '../lib/uploads';
import { computeHashes } from '../lib/hash';

const configuredMaxMb = Number(process.env.NEXT_PUBLIC_PDF_MAX_MB);
const DEFAULT_MAX_MB = Number.isFinite(configuredMaxMb) && configuredMaxMb > 0 ? configuredMaxMb : 100;
const MAX_BYTES = DEFAULT_MAX_MB * 1024 * 1024;

function formatBytes(bytes: number): string {
  if (bytes >= 1024 * 1024) {
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }

  if (bytes >= 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`;
  }

  return `${bytes} B`;
}

function isPdf(file: File): boolean {
  if (file.type) {
    return file.type === 'application/pdf';
  }

  return file.name.toLowerCase().endsWith('.pdf');
}

interface UploadState {
  status: string;
  error: string | null;
  progress: number;
  jobId: string | null;
  requestId: string | null;
}

const initialState: UploadState = {
  status: 'Drop a PDF to begin',
  error: null,
  progress: 0,
  jobId: null,
  requestId: null,
};

export default function UploadPanel() {
  const [state, setState] = useState<UploadState>(initialState);
  const [isBusy, setIsBusy] = useState(false);

  const onDrop = useCallback(
    async (accepted: File[], rejections: FileRejection[]) => {
      if (rejections.length > 0) {
        const rejection = rejections[0];
        if (rejection.errors.some((err) => err.code === 'file-too-large')) {
          setState((prev) => ({
            ...prev,
            error: `PDF must be ${DEFAULT_MAX_MB} MB or smaller.`,
            status: 'File too large',
          }));
          return;
        }

        setState((prev) => ({
          ...prev,
          error: 'Only PDF files are accepted.',
          status: 'Upload blocked',
        }));
        return;
      }

      if (!accepted.length) {
        return;
      }

      const file = accepted[0];

      if (!isPdf(file)) {
        setState({
          ...initialState,
          status: 'Upload blocked',
          error: 'Only PDF files are accepted.',
        });
        return;
      }

      if (file.size > MAX_BYTES) {
        setState({
          ...initialState,
          status: 'File too large',
          error: `PDF must be ${DEFAULT_MAX_MB} MB or smaller.`,
        });
        return;
      }

      try {
        setIsBusy(true);
        setState({
          status: 'Calculating checksum…',
          error: null,
          progress: 0,
          jobId: null,
          requestId: null,
        });

        const checksum = await computeHashes(file);

        setState((prev) => ({ ...prev, status: 'Requesting upload authorization…' }));

        const { response: initiateResponse } = await initiateUpload({
          filename: file.name,
          size: file.size,
          contentType: 'application/pdf',
          sha256: checksum.hex,
          sha256Base64: checksum.base64,
        });

        setState((prev) => ({ ...prev, status: 'Uploading to secure storage…' }));

        if (initiateResponse.uploadType === 'single') {
          await uploadSingle(initiateResponse, file, checksum.base64, (progress) =>
            setState((prev) => ({ ...prev, progress }))
          );
        } else {
          await uploadMultipart(initiateResponse, file, (progress) =>
            setState((prev) => ({ ...prev, progress }))
          );
        }

        setState((prev) => ({ ...prev, status: 'Finalizing upload…' }));

        const ingestResult = await ingestPdf({
          sourceKey: initiateResponse.sourceKey,
          filename: file.name,
          size: file.size,
        });

        setState({
          status: 'Upload queued for processing',
          error: null,
          progress: 100,
          jobId: ingestResult.jobId,
          requestId: ingestResult.requestId,
        });
      } catch (error) {
        if (error instanceof UploadError) {
          setState({
            status: 'Upload failed',
            error: error.message,
            progress: 0,
            jobId: null,
            requestId: error.requestId ?? null,
          });
        } else {
          setState({
            status: 'Upload failed',
            error: 'An unexpected error occurred while uploading the PDF.',
            progress: 0,
            jobId: null,
            requestId: null,
          });
        }
      } finally {
        setIsBusy(false);
      }
    },
    []
  );

  const dropzoneOptions = useMemo(
    () => ({
      onDrop,
      accept: { 'application/pdf': ['.pdf'] },
      multiple: false,
      maxSize: MAX_BYTES,
    }),
    [onDrop]
  );

  return (
    <div className="upload-panel">
      <Dropzone {...dropzoneOptions}>
        {({ getRootProps, getInputProps, isDragActive }) => (
          <div
            {...getRootProps({
              className: `upload-dropzone${isDragActive ? ' upload-dropzone--active' : ''}${
                isBusy ? ' upload-dropzone--disabled' : ''
              }`,
            })}
          >
            <input {...getInputProps({ disabled: isBusy })} />
            <p>{isDragActive ? 'Drop the PDF to start the upload' : 'Drag & drop a PDF here, or click to choose one'}</p>
            <p className="upload-hint">Maximum size: {formatBytes(MAX_BYTES)}</p>
          </div>
        )}
      </Dropzone>

      <div className="upload-status">
        <p><strong>Status:</strong> {state.status}</p>
        {state.progress > 0 && (
          <div className="upload-progress">
            <div className="upload-progress__bar" style={{ width: `${state.progress}%` }} />
          </div>
        )}
        {state.error && <p className="upload-error">{state.error}</p>}
        {state.jobId && (
          <p className="upload-success">Job {state.jobId} is queued.</p>
        )}
        {state.requestId && (
          <p className="upload-meta">Request ID: {state.requestId}</p>
        )}
      </div>

      <style jsx>{`
        .upload-panel {
          display: flex;
          flex-direction: column;
          gap: 16px;
        }
        .upload-dropzone {
          border: 2px dashed #1976d2;
          border-radius: 12px;
          padding: 32px;
          text-align: center;
          transition: background 0.2s ease;
          cursor: pointer;
        }
        .upload-dropzone--active {
          background: rgba(25, 118, 210, 0.08);
        }
        .upload-dropzone--disabled {
          opacity: 0.5;
          cursor: not-allowed;
        }
        .upload-hint {
          margin-top: 8px;
          color: #555;
        }
        .upload-status {
          background: #f5f5f5;
          border-radius: 12px;
          padding: 16px;
        }
        .upload-progress {
          margin-top: 12px;
          background: #e0e0e0;
          border-radius: 6px;
          height: 8px;
          overflow: hidden;
        }
        .upload-progress__bar {
          height: 100%;
          background: #1976d2;
          transition: width 0.2s ease;
        }
        .upload-error {
          color: #c62828;
          margin-top: 12px;
        }
        .upload-success {
          color: #2e7d32;
          margin-top: 12px;
        }
        .upload-meta {
          color: #666;
          margin-top: 4px;
          font-size: 0.875rem;
        }
      `}</style>
    </div>
  );
}

async function uploadSingle(
  response: InitiateSingleUploadResponse,
  file: File,
  sha256Base64: string,
  onProgress: (value: number) => void
) {
  try {
    await uploadSingleWithProgress(response.url, file, sha256Base64, onProgress);
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Upload failed.';
    if (message.toLowerCase().includes('network')) {
      throw new UploadError('Network error while uploading the PDF to storage.');
    }

    const statusMatch = message.match(/Upload failed:\s*(\d{3})/);
    if (statusMatch) {
      throw new UploadError(`Storage rejected the upload (status ${statusMatch[1]}). Please retry.`);
    }

    throw new UploadError('Failed to upload PDF to storage. Please retry.');
  }
}

async function uploadMultipart(
  response: InitiateMultipartUploadResponse,
  file: File,
  onProgress: (value: number) => void
) {
  const partSize = response.partSize;
  const etags: Array<{ partNumber: number; etag: string }> = [];
  let uploadedBytes = 0;

  for (const part of response.parts) {
    const start = (part.partNumber - 1) * partSize;
    const end = Math.min(start + partSize, file.size);
    const chunk = file.slice(start, end);

    let etag: string;

    try {
      etag = await uploadPartWithRetry(part.url, chunk, part.partNumber);
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Multipart upload failed.';
      throw new UploadError(message);
    }

    etags.push({ partNumber: part.partNumber, etag });
    uploadedBytes += chunk.size;
    onProgress(Math.round((uploadedBytes / file.size) * 100));
  }

  await completeMultipartUpload({
    uploadId: response.uploadId,
    sourceKey: response.sourceKey,
    parts: etags,
  });

  onProgress(100);
}

async function uploadSingleWithProgress(
  url: string,
  file: File,
  sha256Base64: string,
  onProgress: (percent: number) => void
): Promise<void> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();

    xhr.upload.addEventListener('loadstart', () => onProgress(0));
    xhr.upload.addEventListener('progress', (event) => {
      if (event.lengthComputable) {
        onProgress(Math.round((event.loaded / event.total) * 100));
      }
    });
    xhr.upload.addEventListener('loadend', () => onProgress(100));

    xhr.addEventListener('load', () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve();
      } else {
        reject(new Error(`Upload failed: ${xhr.status}`));
      }
    });

    xhr.addEventListener('error', () => reject(new Error('Network error while uploading the PDF to storage.')));

    xhr.open('PUT', url);
    xhr.setRequestHeader('Content-Type', 'application/pdf');
    xhr.setRequestHeader('x-amz-checksum-sha256', sha256Base64);
    xhr.send(file);
  });
}

export async function uploadPartWithRetry(
  url: string,
  chunk: Blob,
  partNumber: number,
  maxRetries = 3
): Promise<string> {
  const normalizeEtag = (etag: string) => etag.replace(/^"|"$/g, '');

  for (let attempt = 0; attempt < maxRetries; attempt += 1) {
    try {
      const response = await fetch(url, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/pdf' },
        body: chunk,
      });

      if (response.ok) {
        const etag = response.headers.get('etag');
        if (!etag) {
          throw new Error('Missing ETag');
        }

        return normalizeEtag(etag);
      }

      if (response.status < 500) {
        throw new Error(`Part ${partNumber}: ${response.status}`);
      }
    } catch (error) {
      if (attempt === maxRetries - 1) {
        throw error;
      }

      await new Promise((resolve) => setTimeout(resolve, 1000 * 2 ** attempt));
    }
  }

  throw new Error(`Part ${partNumber} failed after ${maxRetries} attempts`);
}
