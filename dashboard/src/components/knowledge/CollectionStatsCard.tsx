import type { CollectionStats } from '../../api/types';
import { StatCard } from '../shared/StatCard';
import { StatusBadge } from '../shared/StatusBadge';

interface CollectionStatsCardProps {
  stats: CollectionStats;
}

export function CollectionStatsCard({ stats }: CollectionStatsCardProps) {
  return (
    <div
      style={{
        background: '#1a1a2e',
        border: '1px solid #2d2d44',
        borderRadius: 8,
        padding: 16,
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
        <span style={{ fontFamily: 'monospace', color: '#7c4dff', fontWeight: 600 }}>
          {stats.collection_name}
        </span>
        <StatusBadge status={stats.status} />
      </div>
      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
        <StatCard label="Points" value={stats.points_count.toLocaleString()} />
        <StatCard label="Vectors" value={stats.vectors_count.toLocaleString()} />
        <StatCard label="Indexed" value={stats.indexed ? 'Yes' : 'No'} />
      </div>
    </div>
  );
}
