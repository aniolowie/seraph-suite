interface EmptyStateProps {
  message: string;
  hint?: string;
}

export function EmptyState({ message, hint }: EmptyStateProps) {
  return (
    <div style={{ textAlign: 'center', color: '#666', padding: '48px 24px' }}>
      <div style={{ fontSize: 16, marginBottom: 8 }}>{message}</div>
      {hint && <div style={{ fontSize: 13, color: '#444' }}>{hint}</div>}
    </div>
  );
}
