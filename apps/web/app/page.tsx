import UploadPanel from '../src/components/UploadPanel';

export default function HomePage() {
  return (
    <main style={{ maxWidth: 720, margin: '40px auto', padding: 16 }}>
      <h1>Ledger Lift</h1>
      <p style={{ color: '#555', lineHeight: 1.6 }}>
        Ledger Lift helps you convert PDFs by uploading them directly to secure object storage. Start by
        using the uploader below.
      </p>
      <div style={{ marginTop: 32 }}>
        <UploadPanel />
      </div>
    </main>
  );
}
