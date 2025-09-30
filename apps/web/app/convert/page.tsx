import dynamic from 'next/dynamic';

const UploadPanel = dynamic(() => import('../../src/components/UploadPanel'), { ssr: false });

export default function ConvertPage() {
  return (
    <div style={{ padding: 24 }}>
      <h1>PDF → Excel Schedules (Beta)</h1>
      <p>Upload a PDF; we will detect financial schedules and export an .xlsx workbook.</p>
      <UploadPanel />
    </div>
  );
}
