import { useNavigate } from 'react-router-dom';
import { useEngagements } from '../hooks/useEngagements';
import { useBenchmarkRuns } from '../hooks/useBenchmarks';
import { useKnowledgeStats } from '../hooks/useKnowledge';
import { useLearningStats } from '../hooks/useLearning';
import { EngagementCard } from '../components/engagement/EngagementCard';
import { StatCard } from '../components/shared/StatCard';
import { LoadingSpinner } from '../components/shared/LoadingSpinner';
import { EmptyState } from '../components/shared/EmptyState';

export function DashboardPage() {
  const navigate = useNavigate();
  const { data: engagements, isLoading: engLoading } = useEngagements();
  const { data: runs } = useBenchmarkRuns();
  const { data: kb } = useKnowledgeStats();
  const { data: learning } = useLearningStats();

  const latestRun = runs?.[0];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 28 }}>
      {/* Summary stats */}
      <section>
        <h2 style={{ color: '#888', fontSize: 12, textTransform: 'uppercase', letterSpacing: 1, margin: '0 0 12px' }}>
          Overview
        </h2>
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
          <StatCard label="Active Engagements" value={engagements?.length ?? 0} />
          <StatCard label="Benchmark Runs" value={runs?.length ?? 0} />
          <StatCard label="KB Documents" value={kb?.collection.points_count.toLocaleString() ?? '—'} />
          <StatCard label="Learning Triplets" value={learning?.triplets_total ?? '—'} />
          {latestRun && (
            <StatCard
              label="Last Solve Rate"
              value={`${(latestRun.solve_rate * 100).toFixed(1)}%`}
              trend={latestRun.run_id}
            />
          )}
        </div>
      </section>

      {/* Active engagements */}
      <section>
        <h2 style={{ color: '#888', fontSize: 12, textTransform: 'uppercase', letterSpacing: 1, margin: '0 0 12px' }}>
          Active Engagements
        </h2>
        {engLoading ? (
          <LoadingSpinner />
        ) : engagements && engagements.length > 0 ? (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 12 }}>
            {engagements.map((e) => (
              <EngagementCard
                key={e.engagement_id}
                engagement={e}
                onClick={() => navigate(`/engagements/${e.engagement_id}`)}
              />
            ))}
          </div>
        ) : (
          <EmptyState message="No active engagements" hint="Run `seraph bench` to start a benchmark." />
        )}
      </section>
    </div>
  );
}
