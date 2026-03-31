import { useQuery } from '@tanstack/react-query';
import { api } from '../api/client';
import type { LearningStatsResponse, TrainingResultResponse } from '../api/types';

export function useLearningStats() {
  return useQuery<LearningStatsResponse>({
    queryKey: ['learning', 'stats'],
    queryFn: () => api.get<LearningStatsResponse>('/api/learning/stats'),
    refetchInterval: 30000,
  });
}

export function useTrainingHistory() {
  return useQuery<TrainingResultResponse[]>({
    queryKey: ['learning', 'training-history'],
    queryFn: () => api.get<TrainingResultResponse[]>('/api/learning/training-history'),
  });
}
