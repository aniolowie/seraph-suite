const COLOR_MAP: Record<string, string> = {
  solved: '#4caf50',
  partial: '#ff9800',
  failed: '#f44336',
  timeout: '#9e9e9e',
  error: '#e91e63',
  recon: '#2196f3',
  enumerate: '#03a9f4',
  exploit: '#ff5722',
  privesc: '#9c27b0',
  post: '#607d8b',
  done: '#4caf50',
  ok: '#4caf50',
  degraded: '#ff9800',
  green: '#4caf50',
  yellow: '#ff9800',
  red: '#f44336',
};

interface StatusBadgeProps {
  status: string;
  className?: string;
}

export function StatusBadge({ status, className = '' }: StatusBadgeProps) {
  const color = COLOR_MAP[status.toLowerCase()] ?? '#9e9e9e';
  return (
    <span
      className={`status-badge ${className}`}
      style={{
        display: 'inline-block',
        padding: '2px 10px',
        borderRadius: 12,
        fontSize: 12,
        fontWeight: 600,
        background: `${color}22`,
        color,
        border: `1px solid ${color}66`,
        textTransform: 'capitalize',
      }}
    >
      {status}
    </span>
  );
}
