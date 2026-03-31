import { render, screen } from '@testing-library/react';
import { StatCard } from '../../components/shared/StatCard';

describe('StatCard', () => {
  it('renders label and value', () => {
    render(<StatCard label="Solve Rate" value="75.0%" />);
    expect(screen.getByText('Solve Rate')).toBeInTheDocument();
    expect(screen.getByText('75.0%')).toBeInTheDocument();
  });

  it('renders trend when provided', () => {
    render(<StatCard label="Label" value={42} trend="+5%" />);
    expect(screen.getByText('+5%')).toBeInTheDocument();
  });

  it('does not render trend element when omitted', () => {
    render(<StatCard label="Label" value={42} />);
    expect(screen.queryByText(/\+/)).toBeNull();
  });
});
