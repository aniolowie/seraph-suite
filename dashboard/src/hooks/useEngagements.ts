import { useQuery } from '@tanstack/react-query';
import { api } from '../api/client';
import type { EngagementDetail, EngagementSummary } from '../api/types';

export function useEngagements() {
  return useQuery<EngagementSummary[]>({
    queryKey: ['engagements'],
    queryFn: () => api.get<EngagementSummary[]>('/api/engagements'),
    refetchInterval: 5000,
  });
}

export function useEngagement(id: string) {
  return useQuery<EngagementDetail>({
    queryKey: ['engagements', id],
    queryFn: () => api.get<EngagementDetail>(`/api/engagements/${id}`),
    refetchInterval: 5000,
    enabled: Boolean(id),
  });
}
