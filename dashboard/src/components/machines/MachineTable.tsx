import type { MachineResponse } from '../../api/types';
import { StatusBadge } from '../shared/StatusBadge';

interface MachineTableProps {
  machines: MachineResponse[];
  onDelete?: (name: string) => void;
}

export function MachineTable({ machines, onDelete }: MachineTableProps) {
  if (machines.length === 0) {
    return <div style={{ color: '#555', fontSize: 13 }}>No machines registered.</div>;
  }
  return (
    <div style={{ overflowX: 'auto' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
        <thead>
          <tr style={{ color: '#666', textAlign: 'left', borderBottom: '1px solid #2d2d44' }}>
            <th style={{ padding: '8px 12px' }}>Name</th>
            <th style={{ padding: '8px 12px' }}>IP</th>
            <th style={{ padding: '8px 12px' }}>OS</th>
            <th style={{ padding: '8px 12px' }}>Difficulty</th>
            <th style={{ padding: '8px 12px' }}>Techniques</th>
            <th style={{ padding: '8px 12px' }}>Real Flags</th>
            {onDelete && <th style={{ padding: '8px 12px' }} />}
          </tr>
        </thead>
        <tbody>
          {machines.map((m) => (
            <tr key={m.name} style={{ borderBottom: '1px solid #1e1e2e', color: '#ccc' }}>
              <td style={{ padding: '8px 12px', fontWeight: 600 }}>{m.name}</td>
              <td style={{ padding: '8px 12px', fontFamily: 'monospace', color: '#7c4dff' }}>{m.ip}</td>
              <td style={{ padding: '8px 12px', color: '#888' }}>{m.os}</td>
              <td style={{ padding: '8px 12px' }}>
                <StatusBadge status={m.difficulty.toLowerCase()} />
              </td>
              <td style={{ padding: '8px 12px', fontSize: 11, color: '#666' }}>
                {m.expected_techniques.join(', ') || '—'}
              </td>
              <td style={{ padding: '8px 12px' }}>
                <StatusBadge status={m.has_real_flags ? 'ok' : 'degraded'} />
              </td>
              {onDelete && (
                <td style={{ padding: '8px 12px' }}>
                  <button
                    onClick={() => onDelete(m.name)}
                    style={{
                      background: 'transparent',
                      border: '1px solid #f4433666',
                      color: '#f44336',
                      borderRadius: 4,
                      padding: '2px 8px',
                      fontSize: 11,
                      cursor: 'pointer',
                    }}
                  >
                    Delete
                  </button>
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
