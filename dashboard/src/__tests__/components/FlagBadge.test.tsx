import { render, screen } from '@testing-library/react';
import { FlagBadge } from '../../components/engagement/FlagBadge';

describe('FlagBadge', () => {
  it('shows short flag in full', () => {
    render(<FlagBadge flag="abc123" />);
    expect(screen.getByText(/abc123/)).toBeInTheDocument();
  });

  it('truncates long flags', () => {
    const flag = 'a'.repeat(40);
    render(<FlagBadge flag={flag} />);
    // Should not render the full 40-char flag as text content
    expect(screen.queryByText(flag)).toBeNull();
  });

  it('prefixes root flags with #', () => {
    render(<FlagBadge flag="hash" type="root" />);
    expect(screen.getByText(/# /)).toBeInTheDocument();
  });

  it('prefixes user flags with $', () => {
    render(<FlagBadge flag="hash" type="user" />);
    expect(screen.getByText(/\$ /)).toBeInTheDocument();
  });
});
