interface StatCardProps {
  label: string;
  value: string | number;
  trend?: string;
  className?: string;
}

export function StatCard({ label, value, trend, className = '' }: StatCardProps) {
  return (
    <div
      className={`stat-card ${className}`}
      style={{
        background: '#1a1a2e',
        border: '1px solid #2d2d44',
        borderRadius: 8,
        padding: '16px 20px',
        minWidth: 160,
      }}
    >
      <div style={{ color: '#888', fontSize: 12, textTransform: 'uppercase', letterSpacing: 1 }}>
        {label}
      </div>
      <div style={{ color: '#e0e0e0', fontSize: 28, fontWeight: 700, marginTop: 4 }}>{value}</div>
      {trend && <div style={{ color: '#4caf50', fontSize: 12, marginTop: 4 }}>{trend}</div>}
    </div>
  );
}
