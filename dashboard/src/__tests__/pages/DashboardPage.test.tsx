import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { DashboardPage } from '../../pages/DashboardPage';

function wrapper({ children }: { children: React.ReactNode }) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity } },
  });
  return (
    <QueryClientProvider client={client}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  );
}

// All API calls return empty arrays/objects so every query resolves immediately.
beforeEach(() => {
  vi.mocked(global.fetch).mockImplementation((url: RequestInfo | URL) => {
    const path = typeof url === 'string' ? url : url.toString();
    let body: unknown = [];
    if (path.includes('/knowledge/stats')) {
      body = {
        collection: { collection_name: 'seraph_kb', points_count: 0, vectors_count: 0, indexed: true, status: 'green' },
        ingestion: [],
      };
    } else if (path.includes('/learning/stats')) {
      body = {
        feedback_records: 0,
        triplets_total: 0,
        triplets_pending: 0,
        min_triplets_required: 50,
        ready_to_train: false,
        last_training: null,
        training_history: [],
      };
    }
    return Promise.resolve({ ok: true, json: async () => body } as Response);
  });
});

it('renders Overview section', async () => {
  render(<DashboardPage />, { wrapper });
  expect(await screen.findByText('Overview')).toBeInTheDocument();
});

it('renders Active Engagements heading', async () => {
  render(<DashboardPage />, { wrapper });
  const headings = await screen.findAllByText('Active Engagements');
  expect(headings.length).toBeGreaterThanOrEqual(1);
});

it('shows empty state when no engagements', async () => {
  render(<DashboardPage />, { wrapper });
  expect(await screen.findByText(/No active engagements/i, {}, { timeout: 3000 })).toBeInTheDocument();
});
