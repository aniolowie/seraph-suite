import { NavLink } from 'react-router-dom';

const NAV = [
  { to: '/', label: 'Dashboard', exact: true },
  { to: '/benchmarks', label: 'Benchmarks' },
  { to: '/knowledge', label: 'Knowledge Base' },
  { to: '/learning', label: 'Learning Loop' },
  { to: '/machines', label: 'Machines' },
  { to: '/writeups/submit', label: 'Submit Writeup' },
];

export function Sidebar() {
  return (
    <aside
      style={{
        width: 200,
        background: '#12121f',
        borderRight: '1px solid #2d2d44',
        padding: '24px 0',
        display: 'flex',
        flexDirection: 'column',
        gap: 4,
        flexShrink: 0,
      }}
    >
      <div
        style={{ padding: '0 20px 24px', color: '#7c4dff', fontWeight: 700, fontSize: 18 }}
      >
        Seraph
      </div>
      {NAV.map(({ to, label, exact }) => (
        <NavLink
          key={to}
          to={to}
          end={exact}
          style={({ isActive }) => ({
            display: 'block',
            padding: '8px 20px',
            color: isActive ? '#7c4dff' : '#aaa',
            textDecoration: 'none',
            background: isActive ? '#7c4dff11' : 'transparent',
            borderLeft: isActive ? '3px solid #7c4dff' : '3px solid transparent',
            fontSize: 14,
          })}
        >
          {label}
        </NavLink>
      ))}
    </aside>
  );
}
