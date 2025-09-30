export async function computeHashes(file: File): Promise<{ hex: string; base64: string }> {
  const CHUNK_SIZE = 2 * 1024 * 1024; // 2MB chunks
  const chunks: Uint8Array[] = [];

  for (let offset = 0; offset < file.size; offset += CHUNK_SIZE) {
    const chunk = await file
      .slice(offset, Math.min(offset + CHUNK_SIZE, file.size))
      .arrayBuffer();
    chunks.push(new Uint8Array(chunk));
  }

  const totalLength = chunks.reduce((acc, chunk) => acc + chunk.byteLength, 0);
  const combined = new Uint8Array(totalLength);
  let position = 0;
  for (const chunk of chunks) {
    combined.set(chunk, position);
    position += chunk.byteLength;
  }

  const hashBuffer = await crypto.subtle.digest('SHA-256', combined);
  const hashArray = Array.from(new Uint8Array(hashBuffer));

  const hex = hashArray.map((b) => b.toString(16).padStart(2, '0')).join('');
  const binary = String.fromCharCode(...hashArray);
  const base64 = btoa(binary);

  return { hex, base64 };
}
