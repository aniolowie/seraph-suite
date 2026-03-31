import type { Finding } from '../../api/types';

interface FindingsListProps {
  findings: Finding[];
}

export function FindingsList({ findings }: FindingsListProps) {
  if (findings.length === 0) {
    return <div style={{ color: '#555', fontSize: 13 }}>No findings yet.</div>;
  }
  return (
    <div style={{ overflowX: 'auto' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
        <thead>
          <tr style={{ color: '#666', textAlign: 'left', borderBottom: '1px solid #2d2d44' }}>
            <th style={{ padding: '6px 12px' }}>Type</th>
            <th style={{ padding: '6px 12px' }}>Detail</th>
          </tr>
        </thead>
        <tbody>
          {findings.map((f, i) => (
            <tr
              key={i}
              style={{ borderBottom: '1px solid #1e1e2e', color: '#ccc' }}
            >
              <td style={{ padding: '6px 12px', fontFamily: 'monospace', color: '#7c4dff' }}>
                {String(f['type'] ?? 'finding')}
              </td>
              <td style={{ padding: '6px 12px' }}>
                {Object.entries(f)
                  .filter(([k]) => k !== 'type')
                  .map(([k, v]) => `${k}=${String(v)}`)
                  .join('  ')}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
