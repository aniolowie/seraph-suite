import type { MachineResultResponse } from '../../api/types';
import { StatusBadge } from '../shared/StatusBadge';

interface MachineResultRowProps {
  result: MachineResultResponse;
}

function fmtSeconds(s: number): string {
  const m = Math.floor(s / 60);
  const rem = Math.floor(s % 60);
  return m > 0 ? `${m}m ${rem}s` : `${rem}s`;
}

export function MachineResultRow({ result }: MachineResultRowProps) {
  return (
    <tr style={{ borderBottom: '1px solid #1e1e2e', color: '#ccc' }}>
      <td style={{ padding: '8px 12px', fontWeight: 600 }}>{result.name}</td>
      <td style={{ padding: '8px 12px', color: '#888' }}>{result.os}</td>
      <td style={{ padding: '8px 12px' }}>
        <StatusBadge status={result.difficulty.toLowerCase()} />
      </td>
      <td style={{ padding: '8px 12px' }}>
        <StatusBadge status={result.outcome} />
      </td>
      <td style={{ padding: '8px 12px', fontFamily: 'monospace' }}>
        {fmtSeconds(result.total_time_seconds)}
      </td>
      <td style={{ padding: '8px 12px' }}>{result.flags_captured}</td>
      <td style={{ padding: '8px 12px' }}>{(result.technique_accuracy * 100).toFixed(0)}%</td>
      <td style={{ padding: '8px 12px' }}>{(result.kb_utilization * 100).toFixed(0)}%</td>
    </tr>
  );
}
