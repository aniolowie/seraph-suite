import { useQuery } from '@tanstack/react-query';
import { api } from '../api/client';
import type { IngestionSourceStatus, KnowledgeStatsResponse } from '../api/types';

export function useKnowledgeStats() {
  return useQuery<KnowledgeStatsResponse>({
    queryKey: ['knowledge', 'stats'],
    queryFn: () => api.get<KnowledgeStatsResponse>('/api/knowledge/stats'),
  });
}

export function useIngestionStatus() {
  return useQuery<IngestionSourceStatus[]>({
    queryKey: ['knowledge', 'ingestion'],
    queryFn: () => api.get<IngestionSourceStatus[]>('/api/knowledge/ingestion'),
    refetchInterval: 10000,
  });
}
