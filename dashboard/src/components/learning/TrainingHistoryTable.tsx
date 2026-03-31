import type { TrainingResultResponse } from '../../api/types';
import { StatusBadge } from '../shared/StatusBadge';

interface TrainingHistoryTableProps {
  history: TrainingResultResponse[];
}

function fmtDate(iso: string): string {
  return new Date(iso).toLocaleString();
}

export function TrainingHistoryTable({ history }: TrainingHistoryTableProps) {
  if (history.length === 0) {
    return <div style={{ color: '#555', fontSize: 13 }}>No training runs yet.</div>;
  }
  return (
    <div style={{ overflowX: 'auto' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
        <thead>
          <tr style={{ color: '#666', textAlign: 'left', borderBottom: '1px solid #2d2d44' }}>
            <th style={{ padding: '6px 12px' }}>Timestamp</th>
            <th style={{ padding: '6px 12px' }}>Triplets</th>
            <th style={{ padding: '6px 12px' }}>Final Loss</th>
            <th style={{ padding: '6px 12px' }}>Duration</th>
            <th style={{ padding: '6px 12px' }}>Status</th>
          </tr>
        </thead>
        <tbody>
          {history.map((r, i) => (
            <tr key={i} style={{ borderBottom: '1px solid #1e1e2e', color: '#ccc' }}>
              <td style={{ padding: '6px 12px', fontFamily: 'monospace', fontSize: 11 }}>
                {fmtDate(r.timestamp)}
              </td>
              <td style={{ padding: '6px 12px' }}>{r.triplets_used}</td>
              <td style={{ padding: '6px 12px', fontFamily: 'monospace' }}>{r.final_loss.toFixed(4)}</td>
              <td style={{ padding: '6px 12px' }}>{Math.round(r.duration_seconds)}s</td>
              <td style={{ padding: '6px 12px' }}>
                <StatusBadge status={r.success ? 'ok' : 'error'} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
