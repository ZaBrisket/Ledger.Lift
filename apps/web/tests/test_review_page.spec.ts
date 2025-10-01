import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import { ManualReviewPage, type ReviewPageProps } from '../../src/pages/review/[jobId]';

describe('ManualReviewPage', () => {
  const baseSchedules: ReviewPageProps['initialSchedules'] = [
    {
      id: 'rev',
      title: 'Revenue Schedule',
      confidence: 0.42,
      expectedTotal: 1500,
      actualTotal: 1480,
      diff: -20,
      issues: ['Totals are off by $20'],
      include: true,
    },
    {
      id: 'balance',
      title: 'Balance Sheet',
      confidence: 0.91,
      expectedTotal: 0,
      actualTotal: 0,
      diff: 0,
      issues: [],
      include: true,
    },
  ];

  it('renders review summary and schedules', () => {
    const markup = renderToStaticMarkup(
      <ManualReviewPage jobId="demo123" initialSchedules={baseSchedules} />,
    );

    expect(markup).toContain('Manual review');
    expect(markup).toContain('Revenue Schedule');
    expect(markup).toContain('Average confidence');
  });

  it('disables export button when nothing is included', () => {
    const schedules = baseSchedules.map((schedule) => ({ ...schedule, include: false }));
    const markup = renderToStaticMarkup(
      <ManualReviewPage jobId="demo123" initialSchedules={schedules} />,
    );

    expect(markup).toContain('disabled');
  });
});
