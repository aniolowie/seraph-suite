import { render, screen } from '@testing-library/react';
import { PhaseIndicator } from '../../components/engagement/PhaseIndicator';

describe('PhaseIndicator', () => {
  it('renders all phase labels', () => {
    render(<PhaseIndicator currentPhase="recon" />);
    ['recon', 'enumerate', 'exploit', 'privesc', 'post', 'done'].forEach((phase) => {
      expect(screen.getByText(phase)).toBeInTheDocument();
    });
  });

  it('highlights the active phase with bold font', () => {
    render(<PhaseIndicator currentPhase="exploit" />);
    const span = screen.getByText('exploit');
    expect(span.style.fontWeight).toBe('700');
  });

  it('does not crash for unknown phase', () => {
    render(<PhaseIndicator currentPhase="unknown" />);
    expect(screen.getByText('recon')).toBeInTheDocument();
  });
});
