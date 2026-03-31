interface HeaderProps {
  title: string;
}

export function Header({ title }: HeaderProps) {
  return (
    <header
      style={{
        height: 56,
        borderBottom: '1px solid #2d2d44',
        display: 'flex',
        alignItems: 'center',
        padding: '0 24px',
        background: '#12121f',
        flexShrink: 0,
      }}
    >
      <h1 style={{ margin: 0, color: '#e0e0e0', fontSize: 18, fontWeight: 600 }}>{title}</h1>
    </header>
  );
}
