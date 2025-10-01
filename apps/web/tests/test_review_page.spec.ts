import { describe, expect, it } from 'vitest';

import {
  CONFIDENCE_LABELS,
  confidenceLabel,
  computeReviewSummary,
  type ReviewSchedule,
} from '../src/pages/review/[jobId]';

describe('confidenceLabel', () => {
  it('buckets confidence values deterministically', () => {
    expect(confidenceLabel(0.9)).toBe('high');
    expect(confidenceLabel(0.7)).toBe('medium');
    expect(confidenceLabel(0.4)).toBe('low');
  });
});

describe('computeReviewSummary', () => {
  const schedules: ReviewSchedule[] = [
    {
      id: 'income',
      name: 'Income Statement',
      confidence: 0.82,
      diffs: [],
    },
    {
      id: 'balance',
      name: 'Balance Sheet',
      confidence: 0.55,
      diffs: [{ label: 'Assets vs Liabilities', value: 10, expected: 0 }],
    },
  ];

  it('summarizes selected schedules', () => {
    const summary = computeReviewSummary(schedules, new Set(['income']));

    expect(summary.selectedCount).toBe(1);
    expect(summary.flagged).toBe(1);
    expect(summary.averageConfidence).toBeCloseTo(0.82, 2);
  });

  it('handles empty selections gracefully', () => {
    const summary = computeReviewSummary(schedules, new Set());

    expect(summary.selectedCount).toBe(0);
    expect(summary.averageConfidence).toBe(0);
    expect(summary.flagged).toBe(1);
  });
});

describe('confidence labels mapping', () => {
  it('exposes human readable labels', () => {
    expect(CONFIDENCE_LABELS.high).toBe('High');
    expect(CONFIDENCE_LABELS.medium).toBe('Medium');
    expect(CONFIDENCE_LABELS.low).toBe('Low');
  });
});
