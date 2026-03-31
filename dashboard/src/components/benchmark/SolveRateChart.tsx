import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import type { BenchmarkRunResponse } from '../../api/types';

interface SolveRateChartProps {
  runs: BenchmarkRunResponse[];
}

export function SolveRateChart({ runs }: SolveRateChartProps) {
  const data = runs
    .slice()
    .reverse()
    .map((r) => ({
      run: r.run_id.replace('run-', ''),
      solve: Math.round(r.solve_rate * 100),
      partial: Math.round(r.partial_rate * 100),
    }));

  return (
    <ResponsiveContainer width="100%" height={220}>
      <BarChart data={data} margin={{ top: 8, right: 16, left: 0, bottom: 8 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#2d2d44" />
        <XAxis dataKey="run" stroke="#555" tick={{ fontSize: 11 }} />
        <YAxis stroke="#555" tick={{ fontSize: 11 }} unit="%" domain={[0, 100]} />
        <Tooltip
          contentStyle={{ background: '#1a1a2e', border: '1px solid #2d2d44', fontSize: 12 }}
          labelStyle={{ color: '#aaa' }}
        />
        <Bar dataKey="solve" name="Solved" fill="#4caf50" radius={[3, 3, 0, 0]} />
        <Bar dataKey="partial" name="Partial" fill="#ff9800" radius={[3, 3, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}
