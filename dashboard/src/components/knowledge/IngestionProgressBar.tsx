import type { IngestionSourceStatus } from '../../api/types';

interface IngestionProgressBarProps {
  source: IngestionSourceStatus;
}

function fmtDate(iso: string | null): string {
  if (!iso) return 'Never';
  return new Date(iso).toLocaleString();
}

export function IngestionProgressBar({ source }: IngestionProgressBarProps) {
  return (
    <div
      style={{
        background: '#1a1a2e',
        border: '1px solid #2d2d44',
        borderRadius: 6,
        padding: '12px 16px',
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
        <span style={{ color: '#aaa', fontFamily: 'monospace', textTransform: 'uppercase', fontSize: 12 }}>
          {source.source}
        </span>
        <span style={{ color: '#666', fontSize: 12 }}>
          {source.document_count.toLocaleString()} docs
        </span>
      </div>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: '#555' }}>
        <span>Last updated: {fmtDate(source.last_updated)}</span>
        {source.errors > 0 && (
          <span style={{ color: '#f44336' }}>{source.errors} errors</span>
        )}
        {source.active && (
          <span style={{ color: '#7c4dff' }}>Ingesting…</span>
        )}
      </div>
    </div>
  );
}
