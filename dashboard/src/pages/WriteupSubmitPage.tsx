import { useRef, useState } from 'react';
import { api } from '../api/client';
import type { WriteupSubmitResponse, WriteupTaskStatus } from '../api/types';

type Stage = 'idle' | 'uploading' | 'polling' | 'done' | 'error';

export function WriteupSubmitPage() {
  const fileRef = useRef<HTMLInputElement>(null);
  const [stage, setStage] = useState<Stage>('idle');
  const [response, setResponse] = useState<WriteupSubmitResponse | null>(null);
  const [taskStatus, setTaskStatus] = useState<WriteupTaskStatus | null>(null);
  const [errMsg, setErrMsg] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const file = fileRef.current?.files?.[0];
    if (!file) return;

    setStage('uploading');
    setErrMsg('');

    try {
      const res = await api.upload<WriteupSubmitResponse>('/api/writeups', file);
      setResponse(res);
      setStage('polling');
      pollStatus(res.status_url);
    } catch (err) {
      setErrMsg(String(err));
      setStage('error');
    }
  };

  const pollStatus = (url: string) => {
    const interval = setInterval(async () => {
      try {
        const status = await api.get<WriteupTaskStatus>(url);
        setTaskStatus(status);
        if (status.state === 'SUCCESS' || status.state === 'FAILURE') {
          clearInterval(interval);
          setStage(status.state === 'SUCCESS' ? 'done' : 'error');
          if (status.state === 'FAILURE') setErrMsg(status.error || 'Ingestion failed.');
        }
      } catch {
        clearInterval(interval);
        setStage('error');
        setErrMsg('Failed to poll task status.');
      }
    }, 2000);
  };

  const inputStyle: React.CSSProperties = {
    background: '#12121f',
    border: '1px solid #2d2d44',
    borderRadius: 4,
    padding: '8px 12px',
    color: '#e0e0e0',
    fontSize: 13,
    width: '100%',
  };

  return (
    <div style={{ maxWidth: 540 }}>
      <p style={{ color: '#888', fontSize: 13, marginBottom: 20 }}>
        Submit a markdown writeup to contribute to the knowledge base. Accepted: .md files up to 5 MB.
      </p>

      <form onSubmit={(e) => { void handleSubmit(e); }} style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        <input
          ref={fileRef}
          type="file"
          accept=".md,text/markdown,text/plain"
          style={inputStyle}
          disabled={stage === 'uploading' || stage === 'polling'}
        />
        <button
          type="submit"
          disabled={stage === 'uploading' || stage === 'polling'}
          style={{
            background: '#7c4dff',
            color: '#fff',
            border: 'none',
            borderRadius: 4,
            padding: '8px 16px',
            cursor: (stage === 'uploading' || stage === 'polling') ? 'not-allowed' : 'pointer',
            fontSize: 13,
            opacity: (stage === 'uploading' || stage === 'polling') ? 0.6 : 1,
          }}
        >
          {stage === 'uploading' ? 'Uploading…' : stage === 'polling' ? 'Ingesting…' : 'Submit Writeup'}
        </button>
      </form>

      {stage === 'done' && response && (
        <div
          style={{
            marginTop: 16,
            padding: 12,
            background: '#4caf5011',
            border: '1px solid #4caf5044',
            borderRadius: 6,
            color: '#4caf50',
            fontSize: 13,
          }}
        >
          Writeup <strong>{response.filename}</strong> ingested successfully.
        </div>
      )}

      {stage === 'error' && errMsg && (
        <div
          style={{
            marginTop: 16,
            padding: 12,
            background: '#f4433611',
            border: '1px solid #f4433644',
            borderRadius: 6,
            color: '#f44336',
            fontSize: 13,
          }}
        >
          {errMsg}
        </div>
      )}

      {taskStatus && stage === 'polling' && (
        <div style={{ marginTop: 12, color: '#888', fontSize: 12 }}>
          Task {taskStatus.task_id} — {taskStatus.state}
        </div>
      )}
    </div>
  );
}
