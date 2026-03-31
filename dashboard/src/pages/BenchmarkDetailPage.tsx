import { useParams } from 'react-router-dom';
import { useBenchmarkRun } from '../hooks/useBenchmarks';
import { RunSummaryCard } from '../components/benchmark/RunSummaryCard';
import { MachineResultRow } from '../components/benchmark/MachineResultRow';
import { TimeToOwnChart } from '../components/benchmark/TimeToOwnChart';
import { LoadingSpinner } from '../components/shared/LoadingSpinner';
import { ErrorBanner } from '../components/shared/ErrorBanner';

export function BenchmarkDetailPage() {
  const { runId } = useParams<{ runId: string }>();
  const { data: run, isLoading, error } = useBenchmarkRun(runId ?? '');

  if (isLoading) return <LoadingSpinner />;
  if (error) return <ErrorBanner message={String(error)} />;
  if (!run) return null;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 28 }}>
      <div>
        <div style={{ fontFamily: 'monospace', color: '#7c4dff', marginBottom: 4 }}>{run.run_id}</div>
        <div style={{ color: '#555', fontSize: 12 }}>{new Date(run.generated_at).toLocaleString()}</div>
      </div>

      <RunSummaryCard run={run} />

      <section>
        <h2 style={{ color: '#888', fontSize: 12, textTransform: 'uppercase', letterSpacing: 1, margin: '0 0 12px' }}>
          Time to Own
        </h2>
        <TimeToOwnChart run={run} />
      </section>

      <section>
        <h2 style={{ color: '#888', fontSize: 12, textTransform: 'uppercase', letterSpacing: 1, margin: '0 0 12px' }}>
          Per-Machine Results
        </h2>
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <thead>
              <tr style={{ color: '#666', textAlign: 'left', borderBottom: '1px solid #2d2d44' }}>
                <th style={{ padding: '8px 12px' }}>Machine</th>
                <th style={{ padding: '8px 12px' }}>OS</th>
                <th style={{ padding: '8px 12px' }}>Difficulty</th>
                <th style={{ padding: '8px 12px' }}>Outcome</th>
                <th style={{ padding: '8px 12px' }}>Time</th>
                <th style={{ padding: '8px 12px' }}>Flags</th>
                <th style={{ padding: '8px 12px' }}>Technique Acc.</th>
                <th style={{ padding: '8px 12px' }}>KB Util.</th>
              </tr>
            </thead>
            <tbody>
              {run.results.map((r) => (
                <MachineResultRow key={r.name} result={r} />
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section>
        <h2 style={{ color: '#888', fontSize: 12, textTransform: 'uppercase', letterSpacing: 1, margin: '0 0 12px' }}>
          Share
        </h2>
        <a
          href={`/api/benchmarks/${run.run_id}/share`}
          target="_blank"
          rel="noreferrer"
          style={{ color: '#7c4dff', fontSize: 13 }}
        >
          /api/benchmarks/{run.run_id}/share
        </a>
      </section>
    </div>
  );
}
