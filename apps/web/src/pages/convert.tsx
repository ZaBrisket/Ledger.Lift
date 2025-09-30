import Head from 'next/head';
import UploadPanel from '../components/UploadPanel';

export default function ConvertPage() {
  return (
    <>
      <Head>
        <title>Convert PDF • Ledger Lift</title>
        <meta name="description" content="Upload a PDF to Ledger Lift for secure processing." />
      </Head>
      <main style={{ maxWidth: 720, margin: '40px auto', padding: '0 16px' }}>
        <h1>Upload a PDF</h1>
        <p style={{ color: '#555', lineHeight: 1.6 }}>
          Ledger Lift securely stores your PDF in R2/S3 using presigned uploads before processing. Upload a
          PDF to queue it for conversion.
        </p>
        <div style={{ marginTop: 32 }}>
          <UploadPanel />
        </div>
      </main>
    </>
  );
}
