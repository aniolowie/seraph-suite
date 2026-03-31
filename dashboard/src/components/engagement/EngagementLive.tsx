import { useEffect, useRef, useState } from 'react';
import { createEngagementWs, type WsStatus } from '../../api/client';
import type { EngagementDetail, WsMessage } from '../../api/types';
import { FindingsList } from './FindingsList';
import { PhaseIndicator } from './PhaseIndicator';
import { StatusBadge } from '../shared/StatusBadge';

interface EngagementLiveProps {
  engagementId: string;
  initialState?: EngagementDetail;
}

export function EngagementLive({ engagementId, initialState }: EngagementLiveProps) {
  const [state, setState] = useState<EngagementDetail | null>(initialState ?? null);
  const [wsStatus, setWsStatus] = useState<WsStatus>('connecting');
  const cleanupRef = useRef<(() => void) | null>(null);

  useEffect(() => {
    const cleanup = createEngagementWs({
      engagementId,
      onStatusChange: setWsStatus,
      onMessage: (raw) => {
        const msg = raw as WsMessage<EngagementDetail>;
        if (msg.type === 'snapshot' || msg.type === 'update') {
          setState(msg.data);
        }
      },
    });
    cleanupRef.current = cleanup;
    return cleanup;
  }, [engagementId]);

  const indicator = wsStatus === 'open' ? '🟢' : wsStatus === 'connecting' ? '🟡' : '🔴';

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
        <span style={{ fontSize: 12, color: '#666' }}>{indicator} {wsStatus}</span>
      </div>

      {state ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <span style={{ fontFamily: 'monospace', color: '#7c4dff', fontSize: 18 }}>
              {state.target_ip}
            </span>
            <StatusBadge status={state.phase} />
          </div>
          <PhaseIndicator currentPhase={state.phase} />
          <FindingsList findings={state.findings} />
        </div>
      ) : (
        <div style={{ color: '#555' }}>Waiting for engagement data…</div>
      )}
    </div>
  );
}
