import Head from 'next/head';
import type { GetServerSideProps } from 'next';
import { useMemo, useState } from 'react';

type ScheduleDiff = {
  label: string;
  value: number;
  expected?: number;
};

export type ReviewSchedule = {
  id: string;
  name: string;
  confidence: number;
  diffs: ScheduleDiff[];
};

export type ReviewPageProps = {
  jobId: string;
  schedules: ReviewSchedule[];
  featureEnabled: boolean;
};

export const CONFIDENCE_LABELS = {
  high: 'High',
  medium: 'Medium',
  low: 'Low',
} as const;

export function confidenceLabel(confidence: number): keyof typeof CONFIDENCE_LABELS {
  if (confidence >= 0.8) return 'high';
  if (confidence >= 0.6) return 'medium';
  return 'low';
}

export function computeReviewSummary(
  schedules: ReviewSchedule[],
  selected: Set<string>,
): { selectedCount: number; averageConfidence: number; flagged: number } {
  if (schedules.length === 0) {
    return { selectedCount: 0, averageConfidence: 0, flagged: 0 };
  }

  const chosen = schedules.filter((schedule) => selected.has(schedule.id));
  const selectedCount = chosen.length;
  const averageConfidence = chosen.length
    ? chosen.reduce((acc, schedule) => acc + schedule.confidence, 0) / chosen.length
    : 0;
  const flagged = schedules.filter((schedule) => schedule.confidence < 0.6).length;

  return { selectedCount, averageConfidence, flagged };
}

function ReviewPage({ jobId, schedules, featureEnabled }: ReviewPageProps) {
  const [selected, setSelected] = useState<Set<string>>(
    () => new Set(schedules.filter((schedule) => schedule.confidence >= 0.6).map((schedule) => schedule.id)),
  );

  const summary = useMemo(() => computeReviewSummary(schedules, selected), [schedules, selected]);

  if (!featureEnabled) {
    return (
      <main style={{ maxWidth: 860, margin: '32px auto', padding: '0 16px' }}>
        <Head>
          <title>Manual Review Disabled • Ledger Lift</title>
        </Head>
        <h1>Manual review disabled</h1>
        <p>This environment does not have the review UI feature enabled.</p>
      </main>
    );
  }

  return (
    <>
      <Head>
        <title>Manual Review • Ledger Lift</title>
        <meta name="robots" content="noindex" />
      </Head>
      <main style={{ maxWidth: 960, margin: '32px auto', padding: '0 16px' }}>
        <header style={{ marginBottom: 24 }}>
          <h1 style={{ marginBottom: 8 }}>Job {jobId}</h1>
          <p style={{ color: '#555', margin: 0 }}>
            Review detected schedules, adjust the inclusion list, and confirm export-ready data.
          </p>
        </header>

        {summary.flagged > 0 ? (
          <div
            style={{
              border: '1px solid #f0b429',
              background: '#fff7e0',
              padding: '16px',
              borderRadius: 8,
              marginBottom: 24,
            }}
          >
            <strong>{summary.flagged} schedule(s)</strong> require manual attention because of low confidence or
            numeric inconsistencies.
          </div>
        ) : null}

        <section>
          <h2 style={{ fontSize: 20, marginBottom: 12 }}>Schedules</h2>
          {schedules.length === 0 ? (
            <p style={{ color: '#777' }}>No schedules were detected for this job.</p>
          ) : (
            <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
              {schedules.map((schedule) => {
                const included = selected.has(schedule.id);
                const label = confidenceLabel(schedule.confidence);
                return (
                  <li
                    key={schedule.id}
                    style={{
                      border: '1px solid #d0d7de',
                      borderRadius: 8,
                      padding: '16px',
                      marginBottom: 16,
                      background: included ? '#f6f8fa' : 'white',
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <div>
                        <h3 style={{ margin: '0 0 4px 0' }}>{schedule.name}</h3>
                        <span
                          aria-label={`Confidence ${CONFIDENCE_LABELS[label]}`}
                          style={{
                            display: 'inline-block',
                            padding: '4px 8px',
                            borderRadius: 9999,
                            background: label === 'high' ? '#d1f1d3' : label === 'medium' ? '#f5e8a3' : '#f7d6d6',
                            color: '#333',
                            fontSize: 12,
                            fontWeight: 600,
                          }}
                        >
                          {CONFIDENCE_LABELS[label]} • {Math.round(schedule.confidence * 100)}%
                        </span>
                      </div>
                      <button
                        type="button"
                        onClick={() => {
                          setSelected((prev) => {
                            const next = new Set(prev);
                            if (next.has(schedule.id)) {
                              next.delete(schedule.id);
                            } else {
                              next.add(schedule.id);
                            }
                            return next;
                          });
                        }}
                        style={{
                          border: '1px solid #0969da',
                          background: included ? '#0969da' : 'white',
                          color: included ? 'white' : '#0969da',
                          padding: '6px 14px',
                          borderRadius: 6,
                          cursor: 'pointer',
                          fontWeight: 600,
                        }}
                      >
                        {included ? 'Exclude' : 'Include'}
                      </button>
                    </div>
                    {schedule.diffs.length > 0 ? (
                      <table style={{ width: '100%', marginTop: 12, borderCollapse: 'collapse' }}>
                        <thead>
                          <tr style={{ textAlign: 'left', color: '#555', fontSize: 13 }}>
                            <th style={{ paddingBottom: 6 }}>Check</th>
                            <th style={{ paddingBottom: 6 }}>Observed</th>
                            <th style={{ paddingBottom: 6 }}>Expected</th>
                          </tr>
                        </thead>
                        <tbody>
                          {schedule.diffs.map((diff) => (
                            <tr key={diff.label}>
                              <td style={{ padding: '6px 0', borderTop: '1px solid #eaeef2' }}>{diff.label}</td>
                              <td style={{ padding: '6px 0', borderTop: '1px solid #eaeef2' }}>{diff.value.toLocaleString()}</td>
                              <td style={{ padding: '6px 0', borderTop: '1px solid #eaeef2' }}>
                                {diff.expected !== undefined ? diff.expected.toLocaleString() : '—'}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    ) : null}
                  </li>
                );
              })}
            </ul>
          )}
        </section>

        <section style={{ marginTop: 32 }}>
          <h2 style={{ fontSize: 20, marginBottom: 8 }}>Export summary</h2>
          <p style={{ margin: '4px 0', color: '#333' }}>
            <strong>{summary.selectedCount}</strong> schedule(s) selected for export.
          </p>
          <p style={{ margin: '4px 0', color: '#333' }}>
            Average confidence: <strong>{Math.round(summary.averageConfidence * 100)}%</strong>
          </p>
        </section>
      </main>
    </>
  );
}

export const getServerSideProps: GetServerSideProps<ReviewPageProps> = async (context) => {
  const jobId = String(context.params?.jobId ?? 'unknown');
  const featureEnabled = (process.env.FEATURES_T2_REVIEW_UI ?? 'true').toLowerCase() === 'true';

  return {
    props: {
      jobId,
      schedules: [],
      featureEnabled,
    },
  };
};

export default ReviewPage;
