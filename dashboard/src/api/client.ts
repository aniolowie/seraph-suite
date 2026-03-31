// Typed fetch wrapper + WebSocket hook for the Seraph API.

const BASE_URL = import.meta.env.VITE_API_URL ?? '';

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { 'Content-Type': 'application/json', ...init?.headers },
    ...init,
  });
  if (!res.ok) {
    const body = await res.text();
    throw new ApiError(res.status, body);
  }
  return res.json() as Promise<T>;
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body: unknown) =>
    request<T>(path, { method: 'POST', body: JSON.stringify(body) }),
  delete: (path: string) => request<void>(path, { method: 'DELETE' }),

  // File upload (no Content-Type override — browser sets multipart boundary)
  upload: async <T>(path: string, file: File): Promise<T> => {
    const fd = new FormData();
    fd.append('file', file);
    const res = await fetch(`${BASE_URL}${path}`, { method: 'POST', body: fd });
    if (!res.ok) {
      const body = await res.text();
      throw new ApiError(res.status, body);
    }
    return res.json() as Promise<T>;
  },
};

// ── WebSocket hook factory ────────────────────────────────────────────────────

export type WsStatus = 'connecting' | 'open' | 'closed' | 'error';

export interface UseEngagementWsOptions {
  engagementId: string;
  onMessage: (data: unknown) => void;
  onStatusChange?: (status: WsStatus) => void;
}

/**
 * Create and manage a WebSocket connection to the engagement live stream.
 * Returns a cleanup function — call it in a useEffect cleanup.
 */
export function createEngagementWs({
  engagementId,
  onMessage,
  onStatusChange,
}: UseEngagementWsOptions): () => void {
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws';
  const host = import.meta.env.VITE_API_WS_HOST ?? window.location.host;
  const url = `${proto}://${host}/api/engagements/${engagementId}/ws`;

  const ws = new WebSocket(url);
  onStatusChange?.('connecting');

  ws.onopen = () => onStatusChange?.('open');
  ws.onclose = () => onStatusChange?.('closed');
  ws.onerror = () => onStatusChange?.('error');
  ws.onmessage = (event: MessageEvent<string>) => {
    try {
      onMessage(JSON.parse(event.data));
    } catch {
      // ignore non-JSON messages
    }
  };

  return () => ws.close();
}
