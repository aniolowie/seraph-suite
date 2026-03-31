import type { BenchmarkRunResponse } from '../../api/types';
import { StatCard } from '../shared/StatCard';

interface RunSummaryCardProps {
  run: BenchmarkRunResponse;
}

function pct(v: number) {
  return `${(v * 100).toFixed(1)}%`;
}

function fmtSeconds(s: number | null): string {
  if (s === null) return 'N/A';
  const m = Math.floor(s / 60);
  const rem = Math.floor(s % 60);
  return m > 0 ? `${m}m ${rem}s` : `${rem}s`;
}

export function RunSummaryCard({ run }: RunSummaryCardProps) {
  return (
    <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
      <StatCard label="Solve Rate" value={pct(run.solve_rate)} />
      <StatCard label="Partial Rate" value={pct(run.partial_rate)} />
      <StatCard label="Avg Time to Root" value={fmtSeconds(run.avg_time_to_root_seconds)} />
      <StatCard label="Technique Acc." value={pct(run.avg_technique_accuracy)} />
      <StatCard label="KB Utilisation" value={pct(run.avg_kb_utilization)} />
      <StatCard label="Machines" value={run.machine_count} />
    </div>
  );
}
