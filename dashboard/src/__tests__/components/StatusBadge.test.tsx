import { render, screen } from '@testing-library/react';
import { StatusBadge } from '../../components/shared/StatusBadge';

describe('StatusBadge', () => {
  it('renders the status text', () => {
    render(<StatusBadge status="solved" />);
    expect(screen.getByText('solved')).toBeInTheDocument();
  });

  it('capitalises via CSS text-transform (text node unchanged)', () => {
    render(<StatusBadge status="recon" />);
    expect(screen.getByText('recon')).toBeInTheDocument();
  });
});
