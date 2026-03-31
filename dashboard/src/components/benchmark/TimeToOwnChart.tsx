import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import type { BenchmarkRunResponse } from '../../api/types';

interface TimeToOwnChartProps {
  run: BenchmarkRunResponse;
}

export function TimeToOwnChart({ run }: TimeToOwnChartProps) {
  const data = run.results
    .filter((r) => r.outcome === 'solved' || r.outcome === 'partial')
    .map((r) => ({
      name: r.name,
      minutes: Math.round(r.total_time_seconds / 60),
    }));

  if (data.length === 0) {
    return <div style={{ color: '#555', fontSize: 13, padding: 16 }}>No solved machines to chart.</div>;
  }

  return (
    <ResponsiveContainer width="100%" height={200}>
      <BarChart data={data} layout="vertical" margin={{ top: 4, right: 24, left: 8, bottom: 4 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#2d2d44" />
        <XAxis type="number" stroke="#555" tick={{ fontSize: 11 }} unit="m" />
        <YAxis dataKey="name" type="category" stroke="#555" tick={{ fontSize: 12 }} width={70} />
        <Tooltip
          contentStyle={{ background: '#1a1a2e', border: '1px solid #2d2d44', fontSize: 12 }}
          formatter={(v: number) => [`${v} min`, 'Time to own']}
        />
        <Bar dataKey="minutes" fill="#7c4dff" radius={[0, 3, 3, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}
