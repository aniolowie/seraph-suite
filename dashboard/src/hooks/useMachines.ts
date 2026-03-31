import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../api/client';
import type { MachineCreateRequest, MachineResponse } from '../api/types';

export function useMachines() {
  return useQuery<MachineResponse[]>({
    queryKey: ['machines'],
    queryFn: () => api.get<MachineResponse[]>('/api/machines'),
  });
}

export function useMachine(name: string) {
  return useQuery<MachineResponse>({
    queryKey: ['machines', name],
    queryFn: () => api.get<MachineResponse>(`/api/machines/${name}`),
    enabled: Boolean(name),
  });
}

export function useCreateMachine() {
  const client = useQueryClient();
  return useMutation<MachineResponse, Error, MachineCreateRequest>({
    mutationFn: (body) => api.post<MachineResponse>('/api/machines', body),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ['machines'] });
    },
  });
}

export function useDeleteMachine() {
  const client = useQueryClient();
  return useMutation<void, Error, string>({
    mutationFn: (name) => api.delete(`/api/machines/${name}`),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ['machines'] });
    },
  });
}
