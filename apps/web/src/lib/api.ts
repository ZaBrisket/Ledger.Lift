export function getApiBase(): string {
  return process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
}

export async function presignUpload(filename: string, contentType: string) {
  const res = await fetch(`${getApiBase()}/v1/uploads/presign`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ filename, content_type: contentType }),
  });
  if (!res.ok) throw new Error(`Presign failed: ${res.status}`);
  return res.json();
}

export async function registerDocument(payload: { s3_key: string; original_filename: string }) {
  const res = await fetch(`${getApiBase()}/v1/documents`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(`Register failed: ${res.status}`);
  return res.json();
}

export function getExportUrl(docId: string): string {
  return `${getApiBase()}/v1/documents/${docId}/export.xlsx`;
}

export async function getDocumentArtifacts(docId: string) {
  const res = await fetch(`${getApiBase()}/v1/documents/${docId}/artifacts`);
  if (!res.ok) throw new Error(`Get artifacts failed: ${res.status}`);
  return res.json();
}

export async function updateArtifact(artifactId: string, payload: { payload: any; status?: string }) {
  const res = await fetch(`${getApiBase()}/v1/artifacts/${artifactId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(`Update artifact failed: ${res.status}`);
  return res.json();
}
