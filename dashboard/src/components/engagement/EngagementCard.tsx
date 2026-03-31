import type { EngagementSummary } from '../../api/types';
import { PhaseIndicator } from './PhaseIndicator';
import { StatusBadge } from '../shared/StatusBadge';

interface EngagementCardProps {
  engagement: EngagementSummary;
  onClick?: () => void;
}

function formatElapsed(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return m > 0 ? `${m}m ${s}s` : `${s}s`;
}

export function EngagementCard({ engagement, onClick }: EngagementCardProps) {
  return (
    <div
      onClick={onClick}
      style={{
        background: '#1a1a2e',
        border: '1px solid #2d2d44',
        borderRadius: 8,
        padding: 16,
        cursor: onClick ? 'pointer' : 'default',
        transition: 'border-color 0.15s',
      }}
      onMouseEnter={(e) => {
        if (onClick) (e.currentTarget as HTMLDivElement).style.borderColor = '#7c4dff';
      }}
      onMouseLeave={(e) => {
        (e.currentTarget as HTMLDivElement).style.borderColor = '#2d2d44';
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 10 }}>
        <span style={{ fontFamily: 'monospace', color: '#7c4dff', fontWeight: 700 }}>
          {engagement.target_ip}
        </span>
        <StatusBadge status={engagement.phase} />
      </div>
      <PhaseIndicator currentPhase={engagement.phase} />
      <div style={{ display: 'flex', gap: 20, marginTop: 12, color: '#888', fontSize: 12 }}>
        <span>Flags: <strong style={{ color: '#4caf50' }}>{engagement.flags_captured}</strong></span>
        <span>Findings: <strong style={{ color: '#e0e0e0' }}>{engagement.findings_count}</strong></span>
        <span>Elapsed: <strong style={{ color: '#e0e0e0' }}>{formatElapsed(engagement.elapsed_seconds)}</strong></span>
      </div>
    </div>
  );
}
