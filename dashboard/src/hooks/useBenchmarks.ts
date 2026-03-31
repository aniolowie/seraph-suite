import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../api/client';
import type {
  BenchmarkRunResponse,
  TriggerBenchmarkRequest,
  TriggerBenchmarkResponse,
} from '../api/types';

export function useBenchmarkRuns() {
  return useQuery<BenchmarkRunResponse[]>({
    queryKey: ['benchmarks'],
    queryFn: () => api.get<BenchmarkRunResponse[]>('/api/benchmarks'),
  });
}

export function useBenchmarkRun(runId: string) {
  return useQuery<BenchmarkRunResponse>({
    queryKey: ['benchmarks', runId],
    queryFn: () => api.get<BenchmarkRunResponse>(`/api/benchmarks/${runId}`),
    enabled: Boolean(runId),
  });
}

export function useTriggerBenchmark() {
  const client = useQueryClient();
  return useMutation<TriggerBenchmarkResponse, Error, TriggerBenchmarkRequest>({
    mutationFn: (body) => api.post<TriggerBenchmarkResponse>('/api/benchmarks', body),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ['benchmarks'] });
    },
  });
}
