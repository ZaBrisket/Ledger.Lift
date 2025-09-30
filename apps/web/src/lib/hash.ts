export async function computeHashes(file: File): Promise<{ hex: string; base64: string }> {
  const buffer = await file.arrayBuffer();
  const hashBuffer = await crypto.subtle.digest('SHA-256', buffer);
  const hashBytes = new Uint8Array(hashBuffer);

  let hex = '';
  let binary = '';

  // Iterating over the Uint8Array relies on the downlevelIteration compiler option.
  for (const byte of hashBytes) {
    hex += byte.toString(16).padStart(2, '0');
    binary += String.fromCharCode(byte);
  }

  const base64 = btoa(binary);

  return { hex, base64 };
}
