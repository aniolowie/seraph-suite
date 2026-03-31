import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import type { BenchmarkRunResponse } from '../../api/types';

interface LearningCurveChartProps {
  runs: BenchmarkRunResponse[];
}

export function LearningCurveChart({ runs }: LearningCurveChartProps) {
  const data = runs
    .slice()
    .reverse()
    .map((r, i) => ({
      run: i + 1,
      label: r.run_id.replace('run-', ''),
      solve: Math.round(r.solve_rate * 100),
    }));

  return (
    <ResponsiveContainer width="100%" height={200}>
      <LineChart data={data} margin={{ top: 8, right: 16, left: 0, bottom: 8 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#2d2d44" />
        <XAxis dataKey="run" stroke="#555" tick={{ fontSize: 11 }} label={{ value: 'Run #', position: 'insideBottom', offset: -4, fill: '#555', fontSize: 11 }} />
        <YAxis stroke="#555" tick={{ fontSize: 11 }} unit="%" domain={[0, 100]} />
        <Tooltip
          contentStyle={{ background: '#1a1a2e', border: '1px solid #2d2d44', fontSize: 12 }}
          formatter={(v: number) => [`${v}%`, 'Solve rate']}
          labelFormatter={(_, p) => p[0]?.payload?.label ?? ''}
        />
        <Line type="monotone" dataKey="solve" stroke="#7c4dff" strokeWidth={2} dot={{ fill: '#7c4dff', r: 4 }} />
      </LineChart>
    </ResponsiveContainer>
  );
}
