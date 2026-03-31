const PHASES = ['recon', 'enumerate', 'exploit', 'privesc', 'post', 'done'];

interface PhaseIndicatorProps {
  currentPhase: string;
}

export function PhaseIndicator({ currentPhase }: PhaseIndicatorProps) {
  const idx = PHASES.indexOf(currentPhase.toLowerCase());
  return (
    <div style={{ display: 'flex', gap: 4, alignItems: 'center', flexWrap: 'wrap' }}>
      {PHASES.map((phase, i) => {
        const isActive = i === idx;
        const isDone = i < idx;
        return (
          <span
            key={phase}
            style={{
              padding: '2px 8px',
              borderRadius: 4,
              fontSize: 11,
              fontWeight: isActive ? 700 : 400,
              background: isActive ? '#7c4dff' : isDone ? '#2d2d44' : 'transparent',
              color: isActive ? '#fff' : isDone ? '#666' : '#444',
              border: `1px solid ${isActive ? '#7c4dff' : '#2d2d44'}`,
              textTransform: 'uppercase',
            }}
          >
            {phase}
          </span>
        );
      })}
    </div>
  );
}
