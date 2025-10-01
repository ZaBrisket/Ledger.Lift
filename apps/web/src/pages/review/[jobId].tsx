import Head from 'next/head';
import Link from 'next/link';
import type { GetServerSideProps } from 'next';
import { useMemo, useState } from 'react';

type ScheduleReview = {
  id: string;
  title: string;
  confidence: number; // 0-1
  expectedTotal: number;
  actualTotal: number;
  diff: number;
  issues: string[];
  include?: boolean;
};

export interface ReviewPageProps {
  jobId: string;
  initialSchedules: ScheduleReview[];
}

const demoSchedules: ScheduleReview[] = [
  {
    id: 'income-statement',
    title: 'Income Statement',
    confidence: 0.52,
    expectedTotal: 125_000,
    actualTotal: 124_100,
    diff: -900,
    issues: ['Column totals are off by $900'],
    include: true,
  },
  {
    id: 'balance-sheet',
    title: 'Balance Sheet',
    confidence: 0.83,
    expectedTotal: 0,
    actualTotal: 0,
    diff: 0,
    issues: [],
    include: true,
  },
  {
    id: 'cash-flow',
    title: 'Cash Flow Statement',
    confidence: 0.61,
    expectedTotal: 25_300,
    actualTotal: 25_300,
    diff: 0,
    issues: [],
    include: true,
  },
];

const formatCurrency = (value: number) =>
  new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(
    value,
  );

const formatConfidence = (value: number) => `${Math.round(value * 100)}%`;

const confidenceThreshold = () => {
  const raw =
    process.env.NEXT_PUBLIC_REVIEW_CONFIDENCE_THRESHOLD ??
    process.env.REVIEW_CONFIDENCE_THRESHOLD ??
    '0.6';
  const parsed = Number(raw);
  return Number.isFinite(parsed) ? parsed : 0.6;
};

const featureEnabled = () => {
  const raw =
    (process.env.NEXT_PUBLIC_FEATURES_T2_REVIEW_UI ?? process.env.FEATURES_T2_REVIEW_UI ?? 'true').toString();
  return raw.toLowerCase() !== 'false';
};

export const ManualReviewPage = ({ jobId, initialSchedules }: ReviewPageProps) => {
  const threshold = confidenceThreshold();
  const [schedules, setSchedules] = useState(() =>
    (initialSchedules.length > 0 ? initialSchedules : demoSchedules).map((schedule) => ({
      ...schedule,
      include: schedule.include ?? true,
    })),
  );

  const averageConfidence = useMemo(() => {
    if (schedules.length === 0) {
      return 0;
    }
    const total = schedules.reduce((sum, schedule) => sum + schedule.confidence, 0);
    return total / schedules.length;
  }, [schedules]);

  const reviewRequired = useMemo(
    () => schedules.some((schedule) => schedule.confidence < threshold || schedule.issues.length > 0),
    [schedules, threshold],
  );

  const includedCount = useMemo(() => schedules.filter((schedule) => schedule.include).length, [schedules]);

  if (!featureEnabled()) {
    return (
      <main style={{ maxWidth: 720, margin: '48px auto', padding: '0 16px' }}>
        <Head>
          <title>Manual Review Disabled • Ledger Lift</title>
        </Head>
        <h1>Manual review disabled</h1>
        <p style={{ color: '#555' }}>
          This environment has the T2 review UI feature flag turned off. Enable <code>FEATURES_T2_REVIEW_UI</code>{' '}
          to access manual review controls.
        </p>
        <p>
          <Link href="/convert">Return to conversions</Link>
        </p>
      </main>
    );
  }

  const toggleInclude = (id: string) => {
    setSchedules((current) =>
      current.map((schedule) =>
        schedule.id === id ? { ...schedule, include: !schedule.include } : schedule,
      ),
    );
  };

  const selectHighConfidence = () => {
    setSchedules((current) =>
      current.map((schedule) =>
        schedule.confidence >= threshold && schedule.issues.length === 0
          ? { ...schedule, include: true }
          : schedule,
      ),
    );
  };

  const deselectFlagged = () => {
    setSchedules((current) =>
      current.map((schedule) =>
        schedule.confidence < threshold || schedule.issues.length > 0
          ? { ...schedule, include: false }
          : schedule,
      ),
    );
  };

  const exportDisabled = includedCount === 0;

  return (
    <>
      <Head>
        <title>Review Job {jobId} • Ledger Lift</title>
        <meta name="robots" content="noindex" />
      </Head>
      <main style={{ maxWidth: 960, margin: '32px auto', padding: '0 24px' }}>
        <header style={{ marginBottom: 24 }}>
          <p style={{ fontSize: 14, color: '#666', marginBottom: 4 }}>Job #{jobId}</p>
          <h1 style={{ margin: 0 }}>Manual review</h1>
          <p style={{ color: '#444', marginTop: 8 }}>
            Confirm the schedules that should be exported. Toggle <strong>Include</strong> off for tables that need
            correction.
          </p>
          <section
            style={{
              marginTop: 16,
              display: 'flex',
              gap: 24,
              flexWrap: 'wrap',
            }}
          >
            <div style={{ minWidth: 200 }}>
              <h2 style={{ fontSize: 16, marginBottom: 4 }}>Average confidence</h2>
              <p style={{ fontSize: 24, margin: 0, color: reviewRequired ? '#c25700' : '#146c43' }}>
                {formatConfidence(averageConfidence)}
              </p>
            </div>
            <div style={{ minWidth: 200 }}>
              <h2 style={{ fontSize: 16, marginBottom: 4 }}>Included schedules</h2>
              <p style={{ fontSize: 24, margin: 0 }}>{includedCount}</p>
            </div>
            <div style={{ minWidth: 200 }}>
              <h2 style={{ fontSize: 16, marginBottom: 4 }}>Status</h2>
              <p style={{ fontSize: 16, margin: 0 }}>
                {reviewRequired ? 'Review required — fix highlighted issues.' : 'Looks good to export.'}
              </p>
            </div>
          </section>
        </header>

        <div style={{
          display: 'flex',
          gap: 12,
          marginBottom: 16,
          flexWrap: 'wrap',
        }}>
          <button
            type="button"
            onClick={selectHighConfidence}
            style={{
              padding: '8px 14px',
              borderRadius: 4,
              border: '1px solid #2563eb',
              background: '#2563eb',
              color: '#fff',
              cursor: 'pointer',
            }}
          >
            Select All High Confidence
          </button>
          <button
            type="button"
            onClick={deselectFlagged}
            style={{
              padding: '8px 14px',
              borderRadius: 4,
              border: '1px solid #b45309',
              background: '#fff',
              color: '#b45309',
              cursor: 'pointer',
            }}
          >
            Deselect All Flagged
          </button>
        </div>

        <div style={{ display: 'grid', gap: 20 }}>
          {schedules.map((schedule) => (
            <article
              key={schedule.id}
              style={{
                border: '1px solid #ddd',
                borderRadius: 8,
                padding: 20,
                boxShadow: '0 1px 2px rgba(15, 23, 42, 0.08)',
                background: schedule.confidence < threshold ? '#fff7ed' : '#fff',
              }}
            >
              <header style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div>
                  <h2 style={{ margin: '0 0 4px', fontSize: 18 }}>{schedule.title}</h2>
                  <p style={{ margin: 0, color: '#555' }}>Confidence {formatConfidence(schedule.confidence)}</p>
                </div>
                <button
                  type="button"
                  onClick={() => toggleInclude(schedule.id)}
                  style={{
                    border: '1px solid #0f172a',
                    background: schedule.include ? '#0f172a' : '#fff',
                    color: schedule.include ? '#fff' : '#0f172a',
                    borderRadius: 4,
                    padding: '6px 14px',
                    cursor: 'pointer',
                  }}
                >
                  {schedule.include ? 'Include' : 'Excluded'}
                </button>
              </header>

              <dl
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))',
                  gap: 12,
                  marginTop: 16,
                }}
              >
                <div>
                  <dt style={{ fontSize: 12, textTransform: 'uppercase', color: '#64748b' }}>Extracted total</dt>
                  <dd style={{ margin: 0, fontWeight: 600 }}>{formatCurrency(schedule.actualTotal)}</dd>
                </div>
                <div>
                  <dt style={{ fontSize: 12, textTransform: 'uppercase', color: '#64748b' }}>Computed total</dt>
                  <dd style={{ margin: 0 }}>{formatCurrency(schedule.expectedTotal)}</dd>
                </div>
                <div>
                  <dt style={{ fontSize: 12, textTransform: 'uppercase', color: '#64748b' }}>Difference</dt>
                  <dd style={{ margin: 0 }}>{formatCurrency(schedule.diff)}</dd>
                </div>
              </dl>

              {schedule.issues.length > 0 && (
                <ul style={{ marginTop: 16, paddingLeft: 20, color: '#b45309' }}>
                  {schedule.issues.map((issue) => (
                    <li key={issue}>{issue}</li>
                  ))}
                </ul>
              )}
            </article>
          ))}
        </div>

        <footer style={{ marginTop: 32, display: 'flex', gap: 12 }}>
          <Link
            href="/convert"
            style={{
              padding: '10px 18px',
              borderRadius: 6,
              border: '1px solid #334155',
              color: '#334155',
            }}
          >
            Cancel
          </Link>
          <button
            type="button"
            disabled={exportDisabled}
            style={{
              padding: '10px 20px',
              borderRadius: 6,
              border: 'none',
              background: exportDisabled ? '#cbd5f5' : '#2563eb',
              color: exportDisabled ? '#64748b' : '#fff',
              cursor: exportDisabled ? 'not-allowed' : 'pointer',
            }}
          >
            Export selected schedules
          </button>
        </footer>
      </main>
    </>
  );
};

const ReviewPage = (props: ReviewPageProps) => <ManualReviewPage {...props} />;

export const getServerSideProps: GetServerSideProps<ReviewPageProps> = async ({ params }) => {
  const rawId = params?.jobId;
  const jobId = Array.isArray(rawId) ? rawId[0] : rawId ?? 'preview';
  return {
    props: {
      jobId,
      initialSchedules: demoSchedules,
    },
  };
};

export default ReviewPage;
