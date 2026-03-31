import { useState } from 'react';
import type { MachineCreateRequest } from '../../api/types';

interface MachineFormProps {
  onSubmit: (data: MachineCreateRequest) => void;
  loading?: boolean;
}

const DIFFICULTIES = ['Easy', 'Medium', 'Hard', 'Insane'];

export function MachineForm({ onSubmit, loading = false }: MachineFormProps) {
  const [name, setName] = useState('');
  const [ip, setIp] = useState('');
  const [os, setOs] = useState('Linux');
  const [difficulty, setDifficulty] = useState('Easy');
  const [techniques, setTechniques] = useState('');
  const [error, setError] = useState('');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim() || !ip.trim()) {
      setError('Name and IP are required.');
      return;
    }
    setError('');
    onSubmit({
      name: name.trim(),
      ip: ip.trim(),
      os: os.trim(),
      difficulty,
      expected_techniques: techniques
        .split(',')
        .map((t) => t.trim())
        .filter(Boolean),
    });
  };

  const inputStyle: React.CSSProperties = {
    background: '#12121f',
    border: '1px solid #2d2d44',
    borderRadius: 4,
    padding: '6px 10px',
    color: '#e0e0e0',
    fontSize: 13,
    width: '100%',
  };

  return (
    <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 10, maxWidth: 400 }}>
      {error && <div style={{ color: '#f44336', fontSize: 13 }}>{error}</div>}
      <input placeholder="Name (e.g. Lame)" value={name} onChange={(e) => setName(e.target.value)} style={inputStyle} />
      <input placeholder="IP (e.g. 10.10.10.3)" value={ip} onChange={(e) => setIp(e.target.value)} style={inputStyle} />
      <input placeholder="OS (e.g. Linux)" value={os} onChange={(e) => setOs(e.target.value)} style={inputStyle} />
      <select value={difficulty} onChange={(e) => setDifficulty(e.target.value)} style={inputStyle}>
        {DIFFICULTIES.map((d) => <option key={d} value={d}>{d}</option>)}
      </select>
      <input
        placeholder="Techniques (comma-separated, e.g. T1210,T1068)"
        value={techniques}
        onChange={(e) => setTechniques(e.target.value)}
        style={inputStyle}
      />
      <button
        type="submit"
        disabled={loading}
        style={{
          background: '#7c4dff',
          color: '#fff',
          border: 'none',
          borderRadius: 4,
          padding: '8px 16px',
          cursor: loading ? 'not-allowed' : 'pointer',
          fontSize: 13,
          opacity: loading ? 0.6 : 1,
        }}
      >
        {loading ? 'Adding…' : 'Add Machine'}
      </button>
    </form>
  );
}
