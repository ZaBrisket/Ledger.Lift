import { useEffect, useMemo, useState } from 'react';
import Head from 'next/head';

import { apiClient, QueueDashboard, QueuePriority, QueueSnapshot } from '../../lib/api';

const SHOW_OPS = process.env.NEXT_PUBLIC_SHOW_OPS === 'true';

function formatPriority(priority: QueuePriority) {
  switch (priority) {
    case 'high':
      return 'High';
    case 'low':
      return 'Low';
    case 'dead':
      return 'Dead Letter';
    default:
      return 'Default';
  }
}

function QueueTable({ queues }: { queues: QueueSnapshot[] }) {
  return (
    <table style={{ width: '100%', borderCollapse: 'collapse', marginTop: 16 }}>
      <thead>
        <tr>
          {['Priority', 'Queue', 'Queued', 'In Progress', 'Scheduled', 'Deferred', 'Failed', 'Finished'].map((header) => (
            <th
              key={header}
              style={{
                textAlign: 'left',
                padding: '8px 12px',
                borderBottom: '1px solid #e0e0e0',
                fontWeight: 600,
                fontSize: 14,
              }}
            >
              {header}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {queues.map((queue) => (
          <tr key={`${queue.priority}-${queue.name}`}>
            <td style={{ padding: '8px 12px', borderBottom: '1px solid #f0f0f0' }}>{formatPriority(queue.priority)}</td>
            <td style={{ padding: '8px 12px', borderBottom: '1px solid #f0f0f0', fontFamily: 'monospace' }}>{queue.name}</td>
            <td style={{ padding: '8px 12px', borderBottom: '1px solid #f0f0f0' }}>{queue.size}</td>
            <td style={{ padding: '8px 12px', borderBottom: '1px solid #f0f0f0' }}>{queue.started}</td>
            <td style={{ padding: '8px 12px', borderBottom: '1px solid #f0f0f0' }}>{queue.scheduled}</td>
            <td style={{ padding: '8px 12px', borderBottom: '1px solid #f0f0f0' }}>{queue.deferred}</td>
            <td style={{ padding: '8px 12px', borderBottom: '1px solid #f0f0f0', color: queue.failed > 0 ? '#c62828' : undefined }}>{queue.failed}</td>
            <td style={{ padding: '8px 12px', borderBottom: '1px solid #f0f0f0' }}>{queue.finished}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export default function QueueDashboardPage() {
  const [snapshot, setSnapshot] = useState<QueueDashboard | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!SHOW_OPS) {
      setLoading(false);
      return;
    }

    let cancelled = false;

    const fetchSnapshot = async () => {
      const result = await apiClient.getQueueDashboard();
      if (cancelled) {
        return;
      }

      if (result.success) {
        setSnapshot(result.data);
        setError(null);
      } else {
        setError(result.error.message);
      }
      setLoading(false);
    };

    fetchSnapshot();
    const interval = setInterval(fetchSnapshot, 15000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, []);

  const lastUpdated = useMemo(() => {
    if (!snapshot?.timestamp) {
      return null;
    }
    try {
      return new Date(snapshot.timestamp).toLocaleString();
    } catch (error) {
      return snapshot.timestamp;
    }
  }, [snapshot?.timestamp]);

  if (!SHOW_OPS) {
    return (
      <main style={{ maxWidth: 720, margin: '40px auto', padding: '0 16px' }}>
        <Head>
          <title>Queues • Ledger Lift</title>
        </Head>
        <h1>Operations dashboard disabled</h1>
        <p style={{ color: '#666', lineHeight: 1.6 }}>
          Set <code>NEXT_PUBLIC_SHOW_OPS=true</code> to enable the queue dashboard.
        </p>
      </main>
    );
  }

  return (
    <>
      <Head>
        <title>Queue Dashboard • Ledger Lift</title>
      </Head>
      <main style={{ maxWidth: 960, margin: '40px auto', padding: '0 16px' }}>
        <h1>Queue Dashboard</h1>
        <p style={{ color: '#666', lineHeight: 1.6 }}>
          Monitor queue depth and worker activity. Data refreshes every 15 seconds.
        </p>

        {snapshot?.emergency_stop && (
          <div
            style={{
              marginTop: 16,
              padding: '12px 16px',
              borderRadius: 6,
              backgroundColor: '#fff3cd',
              border: '1px solid #ffeeba',
              color: '#856404',
            }}
          >
            <strong>Emergency stop active.</strong> Jobs are not being processed.
          </div>
        )}

        {loading && (
          <p style={{ marginTop: 24, color: '#555' }}>Loading queue metrics…</p>
        )}

        {!loading && error && (
          <p style={{ marginTop: 24, color: '#c62828' }}>{error}</p>
        )}

        {!loading && !error && snapshot && (
          <div style={{ marginTop: 24 }}>
            <QueueTable queues={snapshot.queues} />
            {lastUpdated && (
              <p style={{ marginTop: 12, color: '#888', fontSize: 12 }}>
                Last updated: {lastUpdated}
              </p>
            )}
          </div>
        )}
      </main>
    </>
  );
}
