import { useNavigate } from 'react-router-dom';
import { useBenchmarkRuns, useTriggerBenchmark } from '../hooks/useBenchmarks';
import { SolveRateChart } from '../components/benchmark/SolveRateChart';
import { LearningCurveChart } from '../components/benchmark/LearningCurveChart';
import { StatusBadge } from '../components/shared/StatusBadge';
import { LoadingSpinner } from '../components/shared/LoadingSpinner';
import { ErrorBanner } from '../components/shared/ErrorBanner';
import { EmptyState } from '../components/shared/EmptyState';

export function BenchmarksPage() {
  const navigate = useNavigate();
  const { data: runs, isLoading, error } = useBenchmarkRuns();
  const trigger = useTriggerBenchmark();

  if (isLoading) return <LoadingSpinner />;
  if (error) return <ErrorBanner message={String(error)} />;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 28 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span style={{ color: '#888', fontSize: 13 }}>{runs?.length ?? 0} runs total</span>
        <button
          onClick={() => trigger.mutate({ run_all: true })}
          disabled={trigger.isPending}
          style={{
            background: '#7c4dff',
            color: '#fff',
            border: 'none',
            borderRadius: 4,
            padding: '8px 16px',
            cursor: trigger.isPending ? 'not-allowed' : 'pointer',
            fontSize: 13,
            opacity: trigger.isPending ? 0.6 : 1,
          }}
        >
          {trigger.isPending ? 'Queuing…' : 'Run All Machines'}
        </button>
      </div>

      {runs && runs.length > 1 && (
        <section>
          <h2 style={{ color: '#888', fontSize: 12, textTransform: 'uppercase', letterSpacing: 1, margin: '0 0 12px' }}>
            Solve Rate History
          </h2>
          <SolveRateChart runs={runs} />
        </section>
      )}

      {runs && runs.length > 1 && (
        <section>
          <h2 style={{ color: '#888', fontSize: 12, textTransform: 'uppercase', letterSpacing: 1, margin: '0 0 12px' }}>
            Learning Curve
          </h2>
          <LearningCurveChart runs={runs} />
        </section>
      )}

      <section>
        <h2 style={{ color: '#888', fontSize: 12, textTransform: 'uppercase', letterSpacing: 1, margin: '0 0 12px' }}>
          All Runs
        </h2>
        {!runs || runs.length === 0 ? (
          <EmptyState message="No benchmark runs yet." hint="Click 'Run All Machines' to start." />
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
              <thead>
                <tr style={{ color: '#666', textAlign: 'left', borderBottom: '1px solid #2d2d44' }}>
                  <th style={{ padding: '8px 12px' }}>Run ID</th>
                  <th style={{ padding: '8px 12px' }}>Date</th>
                  <th style={{ padding: '8px 12px' }}>Machines</th>
                  <th style={{ padding: '8px 12px' }}>Solve Rate</th>
                  <th style={{ padding: '8px 12px' }}>Avg Time</th>
                </tr>
              </thead>
              <tbody>
                {runs.map((r) => (
                  <tr
                    key={r.run_id}
                    onClick={() => navigate(`/benchmarks/${r.run_id}`)}
                    style={{ borderBottom: '1px solid #1e1e2e', color: '#ccc', cursor: 'pointer' }}
                  >
                    <td style={{ padding: '8px 12px', fontFamily: 'monospace', color: '#7c4dff' }}>{r.run_id}</td>
                    <td style={{ padding: '8px 12px', fontSize: 11 }}>{new Date(r.generated_at).toLocaleString()}</td>
                    <td style={{ padding: '8px 12px' }}>{r.machine_count}</td>
                    <td style={{ padding: '8px 12px' }}>
                      <StatusBadge status={r.solve_rate >= 0.8 ? 'ok' : r.solve_rate > 0 ? 'degraded' : 'error'} />
                      {` ${(r.solve_rate * 100).toFixed(1)}%`}
                    </td>
                    <td style={{ padding: '8px 12px' }}>
                      {r.avg_time_to_root_seconds !== null
                        ? `${Math.round(r.avg_time_to_root_seconds / 60)}m`
                        : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
