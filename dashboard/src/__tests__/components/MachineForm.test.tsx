import { render, screen, fireEvent } from '@testing-library/react';
import { MachineForm } from '../../components/machines/MachineForm';

describe('MachineForm', () => {
  it('renders all inputs', () => {
    render(<MachineForm onSubmit={vi.fn()} />);
    expect(screen.getByPlaceholderText(/Name/)).toBeInTheDocument();
    expect(screen.getByPlaceholderText(/IP/)).toBeInTheDocument();
    expect(screen.getByPlaceholderText(/OS/)).toBeInTheDocument();
  });

  it('shows error when submitted with empty name', () => {
    render(<MachineForm onSubmit={vi.fn()} />);
    fireEvent.click(screen.getByText('Add Machine'));
    expect(screen.getByText(/required/i)).toBeInTheDocument();
  });

  it('calls onSubmit with correct data', () => {
    const onSubmit = vi.fn();
    render(<MachineForm onSubmit={onSubmit} />);

    fireEvent.change(screen.getByPlaceholderText(/Name/), { target: { value: 'Lame' } });
    fireEvent.change(screen.getByPlaceholderText(/IP/), { target: { value: '10.10.10.3' } });
    fireEvent.click(screen.getByText('Add Machine'));

    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({ name: 'Lame', ip: '10.10.10.3' }),
    );
  });

  it('shows loading state', () => {
    render(<MachineForm onSubmit={vi.fn()} loading />);
    expect(screen.getByText('Adding…')).toBeInTheDocument();
  });
});
