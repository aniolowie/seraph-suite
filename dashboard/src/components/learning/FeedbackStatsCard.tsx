import type { LearningStatsResponse } from '../../api/types';
import { StatCard } from '../shared/StatCard';

interface FeedbackStatsCardProps {
  stats: LearningStatsResponse;
}

export function FeedbackStatsCard({ stats }: FeedbackStatsCardProps) {
  const readyColor = stats.ready_to_train ? '#4caf50' : '#ff9800';
  return (
    <div>
      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginBottom: 12 }}>
        <StatCard label="Feedback Records" value={stats.feedback_records.toLocaleString()} />
        <StatCard label="Total Triplets" value={stats.triplets_total.toLocaleString()} />
        <StatCard label="Pending Triplets" value={stats.triplets_pending.toLocaleString()} />
        <StatCard label="Min Required" value={stats.min_triplets_required} />
      </div>
      <div
        style={{
          padding: '8px 14px',
          borderRadius: 6,
          background: `${readyColor}11`,
          border: `1px solid ${readyColor}44`,
          color: readyColor,
          fontSize: 13,
          display: 'inline-block',
        }}
      >
        {stats.ready_to_train
          ? `Ready to train (${stats.triplets_pending} triplets pending)`
          : `${stats.min_triplets_required - stats.triplets_pending} more triplets needed`}
      </div>
    </div>
  );
}
