interface ErrorBannerProps {
  message: string;
}

export function ErrorBanner({ message }: ErrorBannerProps) {
  return (
    <div
      role="alert"
      style={{
        background: '#f4433622',
        border: '1px solid #f4433666',
        borderRadius: 6,
        padding: '12px 16px',
        color: '#f44336',
        fontSize: 14,
      }}
    >
      {message}
    </div>
  );
}
