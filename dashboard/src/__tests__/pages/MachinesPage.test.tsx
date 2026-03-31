import { render, screen, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { MachinesPage } from '../../pages/MachinesPage';
import type { MachineResponse } from '../../api/types';

const MACHINES: MachineResponse[] = [
  { name: 'Lame', ip: '10.10.10.3', os: 'Linux', difficulty: 'Easy', expected_techniques: ['T1210'], has_real_flags: false },
  { name: 'Blue', ip: '10.10.10.40', os: 'Windows', difficulty: 'Easy', expected_techniques: [], has_real_flags: false },
];

function wrapper({ children }: { children: React.ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={client}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  );
}

beforeEach(() => {
  vi.mocked(global.fetch).mockResolvedValue({
    ok: true,
    json: async () => MACHINES,
  } as Response);
});

it('shows Add Machine button once data loads', async () => {
  render(<MachinesPage />, { wrapper });
  expect(await screen.findByText(/\+ Add Machine/i)).toBeInTheDocument();
});

it('toggles the form on Add Machine click', async () => {
  render(<MachinesPage />, { wrapper });
  fireEvent.click(await screen.findByText(/\+ Add Machine/i));
  expect(screen.getByText('Cancel')).toBeInTheDocument();
  expect(screen.getByText('New Machine')).toBeInTheDocument();
});
