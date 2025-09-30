export async function computeHashes(file: File): Promise<{ hex: string; base64: string }> {
  const CHUNK = 2 * 1024 * 1024; // 2MB chunks to avoid loading entire file at once
  const chunks: Uint8Array[] = [];

  for (let offset = 0; offset < file.size; offset += CHUNK) {
    const slice = file.slice(offset, Math.min(offset + CHUNK, file.size));
    const buffer = await slice.arrayBuffer();
    chunks.push(new Uint8Array(buffer));
  }

  const totalLength = chunks.reduce((length, chunk) => length + chunk.byteLength, 0);
  const combined = new Uint8Array(totalLength);

  let position = 0;
  for (const chunk of chunks) {
    combined.set(chunk, position);
    position += chunk.byteLength;
  }

  const digestBuffer = await crypto.subtle.digest('SHA-256', combined.buffer);
  const digestArray = Array.from(new Uint8Array(digestBuffer));

  const hex = digestArray.map((byte) => byte.toString(16).padStart(2, '0')).join('');
  const base64 = btoa(String.fromCharCode(...digestArray));

  return { hex, base64 };
}
