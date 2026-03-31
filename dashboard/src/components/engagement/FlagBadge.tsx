interface FlagBadgeProps {
  flag: string;
  type?: 'user' | 'root';
}

export function FlagBadge({ flag, type = 'user' }: FlagBadgeProps) {
  const color = type === 'root' ? '#ff5722' : '#4caf50';
  const display = flag.length > 16 ? `${flag.slice(0, 8)}…${flag.slice(-8)}` : flag;
  return (
    <span
      style={{
        display: 'inline-block',
        padding: '2px 10px',
        borderRadius: 4,
        fontSize: 11,
        fontFamily: 'monospace',
        background: `${color}22`,
        color,
        border: `1px solid ${color}66`,
      }}
      title={flag}
    >
      {type === 'root' ? '# ' : '$ '}
      {display}
    </span>
  );
}
